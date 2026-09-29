"""
Postgres access: engine factory, ORM models, and schema bootstrap.

Multi-tenancy uses a shared schema: every tenant-owned table carries a
`tenant_id` (Day 3). Since Day 4, Postgres itself enforces isolation with
row-level security (RLS). Each data-plane transaction declares its tenant in
a transaction-local setting, `app.tenant_id`, and the `tenant_isolation`
policy hides every row that doesn't match. With no tenant declared, the
answer is zero rows. The data-plane role cannot bypass the policy.

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
TENANT_GUC = "app.tenant_id"  # transaction-local setting read by the RLS policy
RLS_TABLES = ("customers",)  # every tenant-owned table gets the same policy


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

# Why NULLIF: before any set_config, current_setting(..., true) is NULL. After
# a transaction that used set_config(..., is_local => true) ends, the same
# connection reads it back as '' (empty string), and ''::uuid is an error.
# NULLIF turns both "no tenant" states into NULL, and NULL matches no row.
TENANT_PREDICATE = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"


async def apply_tenant_isolation(conn, table: str) -> None:
    """Enable, force, and (re)create the isolation policy on one table."""
    await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    # FORCE makes the policy apply to the table owner too. Superusers still
    # bypass RLS, which is why tenant traffic never uses one.
    await conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    await conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
    await conn.execute(
        text(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({TENANT_PREDICATE}) "        # which existing rows are visible
            f"WITH CHECK ({TENANT_PREDICATE})"    # which new/updated rows are allowed
        )
    )


async def bootstrap_schema(owner_engine: AsyncEngine, app_database_url: str) -> None:
    """Enable pgvector, create tables, create the app role, apply RLS.

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

        for table in RLS_TABLES:
            await apply_tenant_isolation(conn, table)
