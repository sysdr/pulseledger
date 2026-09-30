"""Liveness must stay dependency-free: it answers even before lifespan runs."""
from httpx import ASGITransport, AsyncClient

from app.config import LESSON_DAY
from app.main import create_app


async def test_health_needs_no_dependencies():
    # No lifespan entered: no engine, no Redis. Liveness must still answer.
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "day": LESSON_DAY, "service": "pulseledger-backend"}
