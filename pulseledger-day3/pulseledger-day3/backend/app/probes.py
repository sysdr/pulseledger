"""
Dependency probes. Each one does real work against the real service and
reports what it saw; nothing here is simulated.

- Postgres: server version, pgvector version, and one actual vector
  distance computation (proves the extension is loaded, not just listed).
- Redis: server version plus a write-then-read round trip on a key with a
  short TTL (proves we can store, not just PING).
- App role (Day 3): the restricted data-plane role can log in, is not a
  superuser, and cannot modify the tenant registry.
"""
import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

PROBE_KEY_PREFIX = "pulseledger:probe:"


@dataclass
class ProbeResult:
    ok: bool
    latency_ms: float
    version: str | None = None
    details: dict = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


async def probe_postgres(engine: AsyncEngine, timeout_s: float) -> ProbeResult:
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout_s):
            async with engine.connect() as conn:
                server_version = await conn.scalar(text("SHOW server_version"))
                pgvector = await conn.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
                distance = await conn.scalar(
                    text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")
                )
    except Exception as exc:  # any failure is a failed probe, reported verbatim
        return ProbeResult(ok=False, latency_ms=_elapsed_ms(started),
                           error=f"{type(exc).__name__}: {exc}")

    ok = pgvector is not None and float(distance) == 1.0
    return ProbeResult(
        ok=ok,
        latency_ms=_elapsed_ms(started),
        version=str(server_version).split(" ")[0],
        details={"pgvector": pgvector, "l2_distance_check": float(distance)},
        error=None if ok else "pgvector extension missing or returned a wrong distance",
    )


async def probe_redis(client: Redis, timeout_s: float) -> ProbeResult:
    started = time.perf_counter()
    token = uuid.uuid4().hex
    key = f"{PROBE_KEY_PREFIX}{token}"
    try:
        async with asyncio.timeout(timeout_s):
            info = await client.info("server")
            await client.set(key, token, ex=10)
            echoed = await client.get(key)
            await client.delete(key)
    except Exception as exc:
        return ProbeResult(ok=False, latency_ms=_elapsed_ms(started),
                           error=f"{type(exc).__name__}: {exc}")

    ok = echoed == token
    return ProbeResult(
        ok=ok,
        latency_ms=_elapsed_ms(started),
        version=info.get("redis_version"),
        details={"round_trip": "ok" if ok else "mismatch"},
        error=None if ok else "wrote a value and read back something else",
    )


async def probe_app_role(app_engine: AsyncEngine, timeout_s: float) -> ProbeResult:
    """The data-plane role must be able to log in and must be least-privilege:
    not a superuser, and unable to change the tenant registry."""
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout_s):
            async with app_engine.connect() as conn:
                user, is_super, can_update_tenants = (
                    await conn.execute(
                        text(
                            "SELECT current_user, r.rolsuper, "
                            "has_table_privilege(current_user, 'tenants', 'UPDATE') "
                            "FROM pg_roles r WHERE r.rolname = current_user"
                        )
                    )
                ).one()
    except Exception as exc:
        return ProbeResult(ok=False, latency_ms=_elapsed_ms(started),
                           error=f"{type(exc).__name__}: {exc}")

    ok = not is_super and not can_update_tenants
    return ProbeResult(
        ok=ok,
        latency_ms=_elapsed_ms(started),
        details={"role": user, "superuser": is_super, "can_update_tenants": can_update_tenants},
        error=None if ok else "data-plane role has more privilege than it needs",
    )


async def probe_all(
    engine: AsyncEngine,
    client: Redis,
    timeout_s: float,
    app_engine: AsyncEngine | None = None,
) -> dict[str, ProbeResult]:
    probes = [probe_postgres(engine, timeout_s), probe_redis(client, timeout_s)]
    if app_engine is not None:
        probes.append(probe_app_role(app_engine, timeout_s))
    results = await asyncio.gather(*probes)
    names = ["postgres", "redis", "app_role"][: len(results)]
    return dict(zip(names, results))
