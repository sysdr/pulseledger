"""
Postgres access: engine factory, ORM models, and schema bootstrap.

Day 3 introduces multi-tenancy with a shared schema: every tenant-owned
table carries a `tenant_id`, and uniqueness rules are scoped per tenant.
Tenant traffic runs as a restricted role that can read the tenant registry
but never change it. Today, isolation is enforced by the application's
WHERE clauses; Day 4 moves that guarantee into Postgres itself.

The engine is created inside the app's lifespan rather than at import
time: asyncpg connections belong to the event loop that opened them.
"""
import re
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    make_url,
    text,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TENANT_STATUSES = ("active", "suspended", "closed")


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


class Tenant(Base):
    """The tenant registry. Control-plane data: not itself tenant-scoped."""

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'closed')", name="tenants_status_valid"
        ),
        CheckConstraint("slug ~ '^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$'", name="tenants_slug_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Customer(Base):
    """The first tenant-owned table. Every row belongs to exactly one tenant."""

    __tablename__ = "customers"
    __table_args__ = (
        # Email is unique per tenant, not globally: two businesses can both
        # have a customer called ana@example.com.
        UniqueConstraint("tenant_id", "email", name="customers_tenant_email_key"),
        # Lets future tables use a composite foreign key (tenant_id, customer_id),
        # so a subscription can never point at another tenant's customer.
        UniqueConstraint("tenant_id", "id", name="customers_tenant_id_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(String(254))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def build_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )


_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_SAFE_PASSWORD = re.compile(r"^[A-Za-z0-9_\-.]{8,128}$")

async def bootstrap_schema(owner_engine: AsyncEngine, app_database_url: str) -> None:
    """Enable pgvector, create tables, and create the restricted app role.

    A bootstrap shortcut for development: once money-carrying tables arrive,
    schema changes move to versioned migrations.
    """
    app_url = make_url(app_database_url)
    role, password = app_url.username or "", app_url.password or ""
    if not _IDENT.match(role):
        raise ValueError(f"unsafe application role name: {role!r}")
    if not _SAFE_PASSWORD.match(password):
        raise ValueError("application role password must be 8-128 chars of [A-Za-z0-9_-.]")

    async with owner_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

        exists = await conn.scalar(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
        )
        verb = "ALTER" if exists else "CREATE"
        await conn.execute(
            text(
                f"{verb} ROLE {role} LOGIN PASSWORD '{password}' "
                "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        )

        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        await conn.execute(text(f"GRANT SELECT ON tenants TO {role}"))
        await conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON customers TO {role}"))
