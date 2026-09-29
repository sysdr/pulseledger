"""
Tenancy: who is this request for, and what may it do?

Request path for any tenant-scoped endpoint:

  X-Tenant header ──► look up tenant ──► status gate ──► open a transaction
                                                         as the app role and
                                                         set app.tenant_id for
                                                         THAT transaction only
                                                              │
                                   Postgres RLS filters every row it touches

The tenant is identified by a header today. Authentication replaces that
with a credential later; everything downstream of `resolve_tenant` stays
the same.
"""
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import TENANT_GUC, Customer, Tenant

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


async def tenant_session(
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant),
) -> AsyncIterator[AsyncSession]:
    """A session whose transaction is pinned to one tenant.

    set_config(name, value, is_local => true) scopes the setting to the
    current transaction. When it commits or rolls back, the setting is gone,
    so the pooled connection can't carry this tenant into the next request.
    Routes that write must call `session.commit()`; anything after that
    commit runs with no tenant and sees nothing.
    """
    async with request.app.state.app_sessions() as session:
        await session.execute(select(func.set_config(TENANT_GUC, str(tenant.id), True)))
        yield session


def customers_of(tenant: TenantContext) -> Select[tuple[Customer]]:
    """Customer queries still start here, but it is no longer the guard.

    Row-level security is the guarantee. The explicit filter stays because it
    documents intent, gives the planner a plain predicate on the
    (tenant_id, …) indexes, and keeps working if someone runs the query as a
    role that bypasses RLS (the owner, in a migration or a support script).
    """
    return select(Customer).where(Customer.tenant_id == tenant.id)
