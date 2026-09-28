"""
PulseLedger — Day 2: Dev environment

Day 1 proved the process was alive. Day 2 connects it to the two stateful
services every later lesson depends on — Postgres 17 (with pgvector) and
Redis 7 — and teaches the service to tell the difference between
"I'm running" (liveness) and "I can do my job" (readiness).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import LESSON_DAY, Settings, get_settings
from app.db import ServiceBoot, bootstrap_schema, build_engine
from app.lifecycle import Lifecycle, ServiceState
from app.probes import probe_all


def _state_for(results) -> ServiceState:
    return ServiceState.READY if all(r.ok for r in results.values()) else ServiceState.DEGRADED


def build_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        lifecycle = Lifecycle()
        app.state.lifecycle = lifecycle

        engine = build_engine(settings.database_url)
        redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        app.state.engine = engine
        app.state.redis = redis
        app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)

        # Postgres is required: if this raises, the process refuses to start.
        await bootstrap_schema(engine)

        results = await probe_all(engine, redis, settings.dependency_timeout_s)
        if not results["postgres"].ok:
            raise RuntimeError(f"postgres probe failed at boot: {results['postgres'].error}")

        lifecycle.move_to(_state_for(results))

        async with app.state.sessions() as session:
            session.add(
                ServiceBoot(
                    lesson_day=LESSON_DAY,
                    initial_state=lifecycle.state.value,
                    postgres_version=results["postgres"].version or "unknown",
                    pgvector_version=results["postgres"].details.get("pgvector") or "missing",
                    redis_version=results["redis"].version or "unavailable",
                )
            )
            await session.commit()

        try:
            yield
        finally:
            lifecycle.move_to(ServiceState.STOPPING)
            await redis.aclose()
            await engine.dispose()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="PulseLedger API",
        description="Subscription billing, ledger, and marketplace payouts platform — built one lesson at a time.",
        version="0.2.0",
        lifespan=build_lifespan(settings),
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict:
        """Liveness: the process is up. Touches no dependency, on purpose."""
        return {"status": "ok", "day": LESSON_DAY, "service": "pulseledger-backend"}

    @app.get("/api/ready")
    async def ready(request: Request) -> JSONResponse:
        """Readiness: every dependency answered a real query just now."""
        lifecycle: Lifecycle = request.app.state.lifecycle
        if lifecycle.state in (ServiceState.STARTING, ServiceState.STOPPING):
            return JSONResponse(status_code=503, content={"state": lifecycle.state.value})

        results = await probe_all(
            request.app.state.engine, request.app.state.redis, settings.dependency_timeout_s
        )
        lifecycle.move_to(_state_for(results))

        body = {
            "state": lifecycle.state.value,
            "day": LESSON_DAY,
            "state_changed_at": lifecycle.changed_at.isoformat(),
            "transitions": lifecycle.transitions,
            "stripe_mode": settings.stripe_mode,
            "dependencies": {name: r.as_dict() for name, r in results.items()},
        }
        status = 200 if lifecycle.state is ServiceState.READY else 503
        return JSONResponse(status_code=status, content=body)

    @app.get("/api/boots")
    async def boots(request: Request, limit: int = 5) -> dict:
        """Most recent process starts, read back from Postgres."""
        limit = max(1, min(limit, 50))
        async with request.app.state.sessions() as session:
            rows = (
                await session.scalars(
                    select(ServiceBoot).order_by(ServiceBoot.booted_at.desc()).limit(limit)
                )
            ).all()
        return {
            "boots": [
                {
                    "id": str(r.id),
                    "lesson_day": r.lesson_day,
                    "initial_state": r.initial_state,
                    "postgres_version": r.postgres_version,
                    "pgvector_version": r.pgvector_version,
                    "redis_version": r.redis_version,
                    "booted_at": r.booted_at.isoformat(),
                }
                for r in rows
            ]
        }

    return app


app = create_app()
