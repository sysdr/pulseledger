"""
Tenancy: who is this request for, and what may it do?

Request path for any tenant-scoped endpoint:

  X-Tenant header ──► look up tenant ──► status gate ──► scoped query
                                                         (WHERE tenant_id = …)
                                                         as the app role

The tenant is identified by a header today. Authentication replaces that
with a credential later; everything downstream of `resolve_tenant` stays
the same.
"""
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Customer, Tenant

# Tenant lifecycle. `closed` is terminal: a closed tenant's rows are kept
# (billing records have retention requirements) but nothing can reach them.
TENANT_TRANSITIONS: dict[str, set[str]] = {
    "active": {"suspended", "closed"},
    "suspended": {"active", "closed"},
    "closed": set(),
}

READ_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class TenantContext:
    id: uuid.UUID
    slug: str
    status: str


def can_transition(current: str, target: str) -> bool:
    return target in TENANT_TRANSITIONS.get(current, set())


async def resolve_tenant(
    request: Request,
    x_tenant: str | None = Header(default=None, alias="X-Tenant"),
) -> TenantContext:
    if not x_tenant:
        raise HTTPException(status_code=400, detail="X-Tenant header is required")

    async with request.app.state.app_sessions() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == x_tenant))

    # A closed tenant is indistinguishable from one that never existed.
    if tenant is None or tenant.status == "closed":
        raise HTTPException(status_code=404, detail="unknown tenant")
    if tenant.status == "suspended" and request.method not in READ_METHODS:
        raise HTTPException(status_code=403, detail="tenant is suspended: read-only")

    return TenantContext(id=tenant.id, slug=tenant.slug, status=tenant.status)


async def tenant_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A session on the restricted data-plane role. Writes must commit."""
    async with request.app.state.app_sessions() as session:
        yield session


def customers_of(tenant: TenantContext) -> Select[tuple[Customer]]:
    """The only way routes are allowed to start a customer query.

    Isolation today lives in this one WHERE clause. Any query that skips
    this helper sees every tenant's rows, and nothing in the database stops
    it. Day 4 moves the rule into Postgres so it can't be skipped.
    """
    return select(Customer).where(Customer.tenant_id == tenant.id)
