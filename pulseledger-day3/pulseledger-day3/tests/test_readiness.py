"""Readiness against the real Postgres 17 + pgvector and Redis 7 services."""
from redis.asyncio import Redis

from app.config import LESSON_DAY, Settings
from app.main import create_app

from conftest import running

UNREACHABLE_REDIS = "redis://127.0.0.1:1/0"  # nothing listens on port 1


async def test_ready_when_all_dependencies_answer(client):
    response = await client.get("/api/ready")
    body = response.json()

    assert response.status_code == 200, body
    assert body["state"] == "ready"
    assert body["day"] == LESSON_DAY
    assert body["dependencies"]["postgres"]["ok"] is True
    assert body["dependencies"]["redis"]["ok"] is True


async def test_pgvector_actually_computes(client):
    pg = (await client.get("/api/ready")).json()["dependencies"]["postgres"]

    assert pg["details"]["pgvector"]  # extension version string, e.g. "0.8.1"
    assert pg["details"]["l2_distance_check"] == 1.0


async def test_redis_round_trip_reports_server_version(client):
    rd = (await client.get("/api/ready")).json()["dependencies"]["redis"]

    assert rd["details"]["round_trip"] == "ok"
    assert rd["version"].split(".")[0].isdigit()


async def test_boot_is_recorded_in_postgres(client):
    boots = (await client.get("/api/boots?limit=1")).json()["boots"]

    assert len(boots) == 1
    latest = boots[0]
    assert latest["lesson_day"] == LESSON_DAY
    assert latest["initial_state"] == "ready"
    assert latest["pgvector_version"] != "missing"


async def test_boots_accumulate_across_restarts(settings):
    app = create_app(settings)
    async with running(app) as c:
        first = (await c.get("/api/boots?limit=1")).json()["boots"][0]["id"]
    async with running(app) as c:
        second = (await c.get("/api/boots?limit=1")).json()["boots"][0]["id"]

    assert first != second


async def test_redis_outage_degrades_instead_of_crashing():
    app = create_app(Settings(redis_url=UNREACHABLE_REDIS))
    async with running(app) as c:
        response = await c.get("/api/ready")
        body = response.json()

        assert response.status_code == 503
        assert body["state"] == "degraded"
        assert body["dependencies"]["postgres"]["ok"] is True
        assert body["dependencies"]["redis"]["ok"] is False
        assert body["dependencies"]["redis"]["error"]

        # Liveness is unaffected by a dependency outage.
        assert (await c.get("/api/health")).status_code == 200


async def test_degraded_recovers_to_ready_when_redis_returns(settings):
    app = create_app(Settings(redis_url=UNREACHABLE_REDIS))
    async with running(app) as c:
        assert (await c.get("/api/ready")).json()["state"] == "degraded"

        # Redis "comes back": point the app at the real server.
        broken = app.state.redis
        app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await broken.aclose()

        body = (await c.get("/api/ready")).json()
        assert body["state"] == "ready"
        assert body["transitions"] == 2  # starting->degraded, degraded->ready
