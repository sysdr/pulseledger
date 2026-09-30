"""
Organizations, members, and invitations (Day 5).

A tenant is an organization. People join it through memberships, and a
membership starts as an invitation.

Two planes, same split as Day 3:

  Control plane (owner connection)       Data plane (pulseledger_app + RLS)
  --------------------------------       ----------------------------------
  create an org with its first owner     list members
  claim an owner for an ownerless org    invite, list and revoke invitations
  accept an invitation                   change a member's role, remove one

Accepting is control plane because it crosses the tenant boundary: the
person holding the token isn't a member yet, and their user row may already
exist from another organization.
"""
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Invitation, Membership, Tenant, User
from app.tenancy import TenantContext, resolve_tenant, tenant_session

router = APIRouter(prefix="/api")

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
ROLE_PATTERN = r"^(owner|admin|member)$"
DEFAULT_TTL_S = 7 * 24 * 3600
MAX_TTL_S = 30 * 24 * 3600

# Invitation lifecycle. Everything except pending is terminal.
INVITATION_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"accepted", "revoked", "expired"},
    "accepted": set(),
    "revoked": set(),
    "expired": set(),
}


class PersonIn(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    name: str = Field(min_length=1, max_length=120)


class InviteIn(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    role: str = Field(default="member", pattern=ROLE_PATTERN)
    ttl_seconds: int = Field(default=DEFAULT_TTL_S, ge=1, le=MAX_TTL_S)


class AcceptIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    name: str = Field(min_length=1, max_length=120)


class RoleIn(BaseModel):
    role: str = Field(pattern=ROLE_PATTERN)


class LastOwnerError(Exception):
    pass


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _now() -> datetime:
    return datetime.now(UTC)


def _invitation_out(inv: Invitation, token: str | None = None) -> dict:
    effective = inv.status
    if inv.status == "pending" and inv.expires_at <= _now():
        effective = "expired"  # not yet written back; the next write will record it
    out = {
        "id": str(inv.id),
        "email": inv.email,
        "role": inv.role,
        "status": effective,
        "expires_at": inv.expires_at.isoformat(),
        "created_at": inv.created_at.isoformat(),
    }
    if token is not None:
        out["token"] = token  # returned exactly once, at creation
        out["accept_path"] = f"/invite?token={token}"
    return out


def _member_out(m: Membership, u: User) -> dict:
    return {
        "user_id": str(u.id),
        "email": u.email,
        "name": u.name,
        "role": m.role,
        "joined_at": m.joined_at.isoformat(),
    }


async def upsert_user(session: AsyncSession, email: str, name: str) -> uuid.UUID:
    """Return the user for this email, creating it if needed.

    An existing user keeps their name: an invitation can't rename someone.
    ON CONFLICT DO UPDATE (a no-op update) is used instead of DO NOTHING so
    RETURNING yields the id in both cases.
    """
    stmt = (
        insert(User)
        .values(email=email.lower(), name=name)
        .on_conflict_do_update(index_elements=[User.email], set_={"email": User.email})
        .returning(User.id)
    )
    return (await session.execute(stmt)).scalar_one()


# ------------------------------------------------------------ the one guard


async def change_membership(
    session: AsyncSession, user_id: uuid.UUID, new_role: str | None
) -> Membership:
    """Change a member's role, or remove them (new_role=None).

    Enforces: an organization with owners never loses its last one.
    Locking every owner row first serializes concurrent demotions, and
    Postgres re-checks `role = 'owner'` on rows that changed while we waited,
    so two people can't each demote "the other" owner at the same moment.
    RLS limits both queries to the current tenant.
    """
    owners = (
        await session.scalars(
            select(Membership).where(Membership.role == "owner").with_for_update()
        )
    ).all()
    target = await session.scalar(
        select(Membership).where(Membership.user_id == user_id).with_for_update()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="not a member of this organization")

    losing_owner = target.role == "owner" and new_role != "owner"
    if losing_owner and len(owners) <= 1:
        raise LastOwnerError()

    if new_role is None:
        await session.delete(target)
    else:
        target.role = new_role
    await session.flush()
    return target


# ------------------------------------------------------------ control plane


async def create_owner_membership(
    session: AsyncSession, tenant_id: uuid.UUID, email: str, name: str
) -> tuple[uuid.UUID, Membership]:
    user_id = await upsert_user(session, email, name)
    membership = Membership(tenant_id=tenant_id, user_id=user_id, role="owner")
    session.add(membership)
    await session.flush()
    return user_id, membership


@router.post("/tenants/{slug}/owner", status_code=201)
async def claim_owner(slug: str, body: PersonIn, request: Request) -> dict:
    """Give an ownerless organization its first owner (e.g. orgs from Day 3/4)."""
    async with request.app.state.sessions() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == slug).with_for_update())
        if tenant is None or tenant.status == "closed":
            raise HTTPException(status_code=404, detail="unknown tenant")
        has_owner = await session.scalar(
            select(Membership.id)
            .where(Membership.tenant_id == tenant.id, Membership.role == "owner")
            .limit(1)
        )
        if has_owner:
            raise HTTPException(status_code=409, detail="organization already has an owner")
        user_id, _ = await create_owner_membership(session, tenant.id, body.email, body.name)
        await session.commit()
        return {"tenant": slug, "user_id": str(user_id), "role": "owner"}


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


@router.post("/invitations/preview")
async def preview_invitation(body: TokenIn, request: Request) -> dict:
    """What the token holder is being invited to. Changes nothing.

    POST rather than GET so the token travels in the body, not in a URL that
    ends up in access logs.
    """
    async with request.app.state.sessions() as session:
        row = (
            await session.execute(
                select(Invitation, Tenant)
                .join(Tenant, Tenant.id == Invitation.tenant_id)
                .where(Invitation.token_hash == hash_token(body.token))
            )
        ).first()
    if row is None or row[1].status == "closed":
        raise HTTPException(status_code=404, detail="invitation not found")
    inv, tenant = row
    out = _invitation_out(inv)
    out["organization"] = tenant.name
    out["tenant"] = tenant.slug
    return out


@router.post("/invitations/accept")
async def accept_invitation(body: AcceptIn, request: Request) -> dict:
    async with request.app.state.sessions() as session:
        inv = await session.scalar(
            select(Invitation).where(Invitation.token_hash == hash_token(body.token)).with_for_update()
        )
        if inv is None:
            raise HTTPException(status_code=404, detail="invitation not found")

        tenant = await session.get(Tenant, inv.tenant_id)
        if tenant is None or tenant.status == "closed":
            raise HTTPException(status_code=404, detail="invitation not found")
        if tenant.status == "suspended":
            raise HTTPException(status_code=403, detail="organization is suspended")

        if inv.status != "pending":
            raise HTTPException(status_code=409, detail=f"invitation is {inv.status}")

        if inv.expires_at <= _now():
            inv.status, inv.resolved_at = "expired", _now()
            await session.commit()  # record the transition, then refuse
            raise HTTPException(status_code=410, detail="invitation has expired")

        user_id = await upsert_user(session, inv.email, body.name)
        membership = Membership(tenant_id=inv.tenant_id, user_id=user_id, role=inv.role)
        session.add(membership)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=409, detail="already a member of this organization")

        inv.status, inv.resolved_at, inv.membership_id = "accepted", _now(), membership.id
        await session.commit()
        user = await session.get(User, user_id)
        return {
            "tenant": tenant.slug,
            "organization": tenant.name,
            "user": {"id": str(user.id), "email": user.email, "name": user.name},
            "role": membership.role,
        }


# --------------------------------------------------------------- data plane


@router.get("/members")
async def list_members(
    tenant: TenantContext = Depends(resolve_tenant),
    session: AsyncSession = Depends(tenant_session),
) -> dict:
    rows = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .order_by(Membership.joined_at)
        )
    ).all()
    return {"tenant": tenant.slug, "members": [_member_out(m, u) for m, u in rows]}


@router.patch("/members/{user_id}")
async def update_member(
    user_id: uuid.UUID, body: RoleIn, session: AsyncSession = Depends(tenant_session)
) -> dict:
    try:
        m = await change_membership(session, user_id, body.role)
    except LastOwnerError:
        raise HTTPException(status_code=409, detail="an organization must keep at least one owner")
    await session.commit()
    return {"user_id": str(m.user_id), "role": m.role}


@router.delete("/members/{user_id}", status_code=204)
async def remove_member(user_id: uuid.UUID, session: AsyncSession = Depends(tenant_session)) -> None:
    try:
        await change_membership(session, user_id, None)
    except LastOwnerError:
        raise HTTPException(status_code=409, detail="an organization must keep at least one owner")
    await session.commit()


@router.post("/invitations", status_code=201)
async def create_invitation(
    body: InviteIn,
    tenant: TenantContext = Depends(resolve_tenant),
    session: AsyncSession = Depends(tenant_session),
) -> dict:
    email = body.email.lower()

    # RLS on users means this only finds people already in THIS organization.
    already = await session.scalar(
        select(Membership.id).join(User, User.id == Membership.user_id).where(User.email == email)
    )
    if already:
        raise HTTPException(status_code=409, detail="already a member of this organization")

    # A stale pending invitation would block the partial unique index; retire it.
    await session.execute(
        update(Invitation)
        .where(Invitation.email == email, Invitation.status == "pending", Invitation.expires_at <= _now())
        .values(status="expired", resolved_at=_now())
    )

    token = secrets.token_urlsafe(32)
    inv = Invitation(
        tenant_id=tenant.id,
        email=email,
        role=body.role,
        token_hash=hash_token(token),
        expires_at=_now() + timedelta(seconds=body.ttl_seconds),
    )
    session.add(inv)
    try:
        await session.flush()
        await session.refresh(inv)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="a pending invitation for this email already exists")
    return _invitation_out(inv, token=token)


@router.get("/invitations")
async def list_invitations(
    tenant: TenantContext = Depends(resolve_tenant),
    session: AsyncSession = Depends(tenant_session),
) -> dict:
    rows = (await session.scalars(select(Invitation).order_by(Invitation.created_at.desc()))).all()
    return {"tenant": tenant.slug, "invitations": [_invitation_out(i) for i in rows]}


@router.post("/invitations/{invitation_id}/revoke")
async def revoke_invitation(
    invitation_id: uuid.UUID, session: AsyncSession = Depends(tenant_session)
) -> dict:
    inv = await session.scalar(
        select(Invitation).where(Invitation.id == invitation_id).with_for_update()
    )
    if inv is None:
        raise HTTPException(status_code=404, detail="invitation not found")
    if "revoked" not in INVITATION_TRANSITIONS[inv.status]:
        raise HTTPException(status_code=409, detail=f"invitation is {inv.status}")
    inv.status, inv.resolved_at = "revoked", _now()
    await session.commit()
    return _invitation_out(inv)
