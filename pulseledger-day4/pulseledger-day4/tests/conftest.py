"""
Shared fixtures. ASGITransport does not run FastAPI's lifespan on its own,
so each fixture enters it explicitly. That means every test gets a real
engine, a real Redis client, and a real boot row, then tears them down.

Tests run against a separate real database, `<your db>_test`, created on
first use. Test tenants never show up in the app you're running.
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if BACKEND.exists():
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import make_url, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.config import Settings  # noqa: E402


def _use_test_database() -> None:
    base = Settings()
    owner, app_role = make_url(base.database_url), make_url(base.app_database_url)
    test_db = f"{owner.database}_test"

    async def ensure() -> None:
        engine = create_async_engine(owner, isolation_level="AUTOCOMMIT")
        async with engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": test_db}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{test_db}"'))
        await engine.dispose()

    asyncio.run(ensure())
    os.environ["DATABASE_URL"] = owner.set(database=test_db).render_as_string(hide_password=False)
    os.environ["APP_DATABASE_URL"] = app_role.set(database=test_db).render_as_string(
        hide_password=False
    )


_use_test_database()

from app.main import create_app  # noqa: E402  (imported after the env points at the test DB)


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
async def app(settings):
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
