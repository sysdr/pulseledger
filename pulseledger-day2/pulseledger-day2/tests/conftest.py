"""
Shared fixtures. ASGITransport does not run FastAPI's lifespan on its own,
so each fixture enters it explicitly. That means every test gets a real
engine, a real Redis client, and a real boot row, then tears them down.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if BACKEND.exists():
    sys.path.insert(0, str(BACKEND))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@asynccontextmanager
async def running(app):
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def client(settings):
    app = create_app(settings)
    async with running(app) as c:
        yield c
