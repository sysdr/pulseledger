"""
Postgres access: async engine factory, the first ORM table, and schema
bootstrap.

The engine is created inside the app's lifespan rather than at import
time. asyncpg connections belong to the event loop that opened them, so a
module-level engine breaks as soon as a second loop (a test, a worker)
touches it.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ServiceBoot(Base):
    """One row per process start: which lesson booted, against what versions."""

    __tablename__ = "service_boots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lesson_day: Mapped[int] = mapped_column(Integer)
    initial_state: Mapped[str] = mapped_column(String(16))
    postgres_version: Mapped[str] = mapped_column(String(64))
    pgvector_version: Mapped[str] = mapped_column(String(16))
    redis_version: Mapped[str] = mapped_column(String(32))
    booted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def build_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )


async def bootstrap_schema(engine: AsyncEngine) -> None:
    """Enable pgvector and create today's tables.

    A bootstrap shortcut: once money-carrying tables arrive, schema changes
    move to versioned migrations.
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
