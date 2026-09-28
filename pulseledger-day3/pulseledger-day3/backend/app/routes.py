"""
Day 3 routes.

Control plane (/api/tenants): manages the tenant registry. Uses the owner
connection. Admin-only once authentication exists.

Data plane (/api/customers): tenant-scoped. Uses the restricted app role,
and every customer query starts from `customers_of(tenant)`, which adds
`WHERE tenant_id = …`. That clause is the whole isolation story today.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Customer, Tenant
from app.tenancy import (
    TENANT_TRANSITIONS,
    TenantContext,
    can_transition,
    customers_of,
    resolve_tenant,
    tenant_session,
)

router = APIRouter(prefix="/api")

SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class TenantIn(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=120)


class StatusIn(BaseModel):
    status: str = Field(pattern=r"^(active|suspended|closed)$")


class CustomerIn(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    name: str = Field(min_length=1, max_length=120)


def _tenant_out(t: Tenant, customer_count: int | None = None) -> dict:
    out = {
        "id": str(t.id),
        "slug": t.slug,
        "name": t.name,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
        "status_changed_at": t.status_changed_at.isoformat(),
        "allowed_next": sorted(TENANT_TRANSITIONS[t.status]),
    }
    if customer_count is not None:
        out["customer_count"] = customer_count
    return out


def _customer_out(c: Customer) -> dict:
    return {
        "id": str(c.id),
        "tenant_id": str(c.tenant_id),
        "email": c.email,
        "name": c.name,
        "created_at": c.created_at.isoformat(),
    }


# ---------------------------------------------------------------- control plane


@router.post("/tenants", status_code=201)
async def create_tenant(body: TenantIn, request: Request) -> dict:
    async with request.app.state.sessions() as session:
        tenant = Tenant(slug=body.slug, name=body.name)
        session.add(tenant)
        try:
            await session.commit()
        except IntegrityError:
            raise HTTPException(status_code=409, detail=f"tenant '{body.slug}' already exists")
        await session.refresh(tenant)
        return _tenant_out(tenant, customer_count=0)


@router.get("/tenants")
async def list_tenants(request: Request) -> dict:
    counts = (
        select(Customer.tenant_id, func.count().label("n"))
        .group_by(Customer.tenant_id)
        .subquery()
    )
    async with request.app.state.sessions() as session:
        rows = (
            await session.execute(
                select(Tenant, func.coalesce(counts.c.n, 0))
                .outerjoin(counts, counts.c.tenant_id == Tenant.id)
                .order_by(Tenant.created_at)
            )
        ).all()
    return {"tenants": [_tenant_out(t, n) for t, n in rows]}


@router.patch("/tenants/{slug}/status")
async def change_tenant_status(slug: str, body: StatusIn, request: Request) -> dict:
    async with request.app.state.sessions() as session:
        tenant = await session.scalar(
            select(Tenant).where(Tenant.slug == slug).with_for_update()
        )
        if tenant is None:
            raise HTTPException(status_code=404, detail="unknown tenant")
        if tenant.status == body.status:
            return _tenant_out(tenant)
        if not can_transition(tenant.status, body.status):
            raise HTTPException(
                status_code=409,
                detail=f"cannot move tenant from {tenant.status} to {body.status}",
            )
        tenant.status = body.status
        tenant.status_changed_at = datetime.now(UTC)
        await session.commit()
        return _tenant_out(tenant)


# ------------------------------------------------------------------- data plane


@router.post("/customers", status_code=201)
async def create_customer(
    body: CustomerIn,
    tenant: TenantContext = Depends(resolve_tenant),
    session: AsyncSession = Depends(tenant_session),
) -> dict:
    customer = Customer(tenant_id=tenant.id, email=body.email.lower(), name=body.name)
    session.add(customer)
    try:
        await session.flush()
        await session.refresh(customer)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="a customer with that email already exists")
    return _customer_out(customer)


@router.get("/customers")
async def list_customers(
    tenant: TenantContext = Depends(resolve_tenant),
    session: AsyncSession = Depends(tenant_session),
) -> dict:
    rows = (await session.scalars(customers_of(tenant).order_by(Customer.created_at))).all()
    return {"tenant": tenant.slug, "customers": [_customer_out(c) for c in rows]}


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    tenant: TenantContext = Depends(resolve_tenant),
    session: AsyncSession = Depends(tenant_session),
) -> dict:
    customer = await session.scalar(customers_of(tenant).where(Customer.id == customer_id))
    if customer is None:
        # Another tenant's customer and a nonexistent one look identical.
        raise HTTPException(status_code=404, detail="customer not found")
    return _customer_out(customer)
