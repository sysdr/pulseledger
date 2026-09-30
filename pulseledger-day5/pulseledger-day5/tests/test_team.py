"""
Organizations, members, and invitations, against the real database.

Every test creates uniquely named organizations and email addresses, so the
suite can run repeatedly against the same test database.
"""
import asyncio
import hashlib
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.db import TENANT_GUC, Invitation, Membership, User
from app.team import LastOwnerError, change_membership


def uniq(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def email(label: str) -> str:
    return f"{label}.{uuid.uuid4().hex[:8]}@example.com"


async def make_org(client, label: str, owner: str | None = None) -> dict:
    body = {"slug": uniq(label), "name": label.title()}
    if owner:
        body["owner"] = {"email": owner, "name": "Owner"}
    r = await client.post("/api/tenants", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def invite(client, org: dict, who: str, role: str = "member", ttl: int | None = None):
    body = {"email": who, "role": role}
    if ttl is not None:
        body["ttl_seconds"] = ttl
    return await client.post("/api/invitations", json=body, headers={"X-Tenant": org["slug"]})


async def accept(client, token: str, name: str = "Invitee"):
    return await client.post("/api/invitations/accept", json={"token": token, "name": name})


async def members(client, org: dict) -> list[dict]:
    r = await client.get("/api/members", headers={"X-Tenant": org["slug"]})
    return r.json()["members"]


# ------------------------------------------------------------------ owners


async def test_org_created_with_its_first_owner(client):
    owner = email("ana")
    org = await make_org(client, "north", owner=owner)

    listed = await members(client, org)
    assert [(m["email"], m["role"]) for m in listed] == [(owner, "owner")]


async def test_ownerless_org_can_claim_an_owner_once(client):
    org = await make_org(client, "legacy")  # like an org created on Day 3 or 4
    claim = {"email": email("first"), "name": "First"}

    assert (await client.post(f"/api/tenants/{org['slug']}/owner", json=claim)).status_code == 201
    again = await client.post(f"/api/tenants/{org['slug']}/owner", json={"email": email("x"), "name": "X"})
    assert again.status_code == 409


# ------------------------------------------------------------- invitations


async def test_invite_and_accept_creates_a_membership(client):
    org = await make_org(client, "north", owner=email("owner"))
    who = email("li")

    r = await invite(client, org, who, role="admin")
    assert r.status_code == 201
    token = r.json()["token"]

    joined = await accept(client, token, name="Li Wei")
    assert joined.status_code == 200
    assert joined.json()["role"] == "admin"
    assert (who, "admin") in [(m["email"], m["role"]) for m in await members(client, org)]

    invs = (await client.get("/api/invitations", headers={"X-Tenant": org["slug"]})).json()
    assert invs["invitations"][0]["status"] == "accepted"
    assert "token" not in invs["invitations"][0]


async def test_only_a_hash_of_the_token_is_stored(client, app):
    org = await make_org(client, "north", owner=email("owner"))
    r = await invite(client, org, email("li"))
    token, inv_id = r.json()["token"], r.json()["id"]

    async with app.state.sessions() as session:  # owner connection
        inv = await session.get(Invitation, uuid.UUID(inv_id))
    assert inv.token_hash == hashlib.sha256(token.encode()).digest()
    assert token.encode() not in inv.token_hash


async def test_an_invitation_can_be_used_once(client):
    org = await make_org(client, "north", owner=email("owner"))
    token = (await invite(client, org, email("li"))).json()["token"]

    assert (await accept(client, token)).status_code == 200
    second = await accept(client, token)
    assert second.status_code == 409
    assert second.json()["detail"] == "invitation is accepted"


async def test_one_pending_invitation_per_email(client):
    org = await make_org(client, "north", owner=email("owner"))
    who = email("li")

    assert (await invite(client, org, who)).status_code == 201
    dup = await invite(client, org, who.upper())
    assert dup.status_code == 409


async def test_cannot_invite_an_existing_member(client):
    owner = email("owner")
    org = await make_org(client, "north", owner=owner)

    r = await invite(client, org, owner)
    assert r.status_code == 409
    assert r.json()["detail"] == "already a member of this organization"


async def test_expired_invitation_is_refused_and_recorded(client):
    org = await make_org(client, "north", owner=email("owner"))
    who = email("temp")
    token = (await invite(client, org, who, ttl=1)).json()["token"]
    await asyncio.sleep(1.2)

    r = await accept(client, token)
    assert r.status_code == 410
    again = await accept(client, token)
    assert again.json()["detail"] == "invitation is expired"


async def test_stale_pending_invitation_does_not_block_a_new_one(client):
    org = await make_org(client, "north", owner=email("owner"))
    who = email("temp")
    await invite(client, org, who, ttl=1)
    await asyncio.sleep(1.2)

    # Never accepted, still stored as pending, but past its expiry.
    assert (await invite(client, org, who)).status_code == 201


async def test_revoked_invitation_cannot_be_accepted(client):
    org = await make_org(client, "north", owner=email("owner"))
    r = await invite(client, org, email("contractor"))
    token, inv_id = r.json()["token"], r.json()["id"]

    rv = await client.post(f"/api/invitations/{inv_id}/revoke", headers={"X-Tenant": org["slug"]})
    assert rv.json()["status"] == "revoked"
    assert (await accept(client, token)).json()["detail"] == "invitation is revoked"
    again = await client.post(f"/api/invitations/{inv_id}/revoke", headers={"X-Tenant": org["slug"]})
    assert again.status_code == 409


async def test_unknown_token_is_404(client):
    r = await accept(client, "not-a-real-token-" + "x" * 20)
    assert r.status_code == 404


async def test_suspended_org_cannot_invite_or_be_joined(client):
    org = await make_org(client, "north", owner=email("owner"))
    token = (await invite(client, org, email("li"))).json()["token"]
    await client.patch(f"/api/tenants/{org['slug']}/status", json={"status": "suspended"})

    assert (await invite(client, org, email("other"))).status_code == 403
    assert (await accept(client, token)).status_code == 403


# ---------------------------------------------------- one person, many orgs


async def test_one_user_can_belong_to_two_orgs_with_different_roles(client, app):
    who = email("sam")
    north = await make_org(client, "north", owner=email("o1"))
    south = await make_org(client, "south", owner=email("o2"))

    await accept(client, (await invite(client, north, who, role="admin")).json()["token"], "Sam")
    await accept(client, (await invite(client, south, who, role="member")).json()["token"], "Sam")

    async with app.state.sessions() as session:
        users = await session.scalar(select(func.count()).select_from(User).where(User.email == who))
    assert users == 1

    roles = {
        org["slug"]: next(m["role"] for m in await members(client, org) if m["email"] == who)
        for org in (north, south)
    }
    assert roles == {north["slug"]: "admin", south["slug"]: "member"}


async def test_an_org_sees_only_its_own_people(client, app):
    north_owner, south_owner = email("n"), email("s")
    north = await make_org(client, "north", owner=north_owner)
    await make_org(client, "south", owner=south_owner)

    assert [m["email"] for m in await members(client, north)] == [north_owner]

    async with app.state.app_sessions() as session:
        await session.execute(select(func.set_config(TENANT_GUC, north["id"], True)))
        visible = set((await session.scalars(select(User.email))).all())
    assert visible == {north_owner}


async def test_no_tenant_context_sees_no_users(client, app):
    await make_org(client, "north", owner=email("o"))

    async with app.state.app_sessions() as session:
        n = await session.scalar(select(func.count()).select_from(User))
    assert n == 0


async def test_one_org_cannot_see_or_revoke_anothers_invitations(client):
    north = await make_org(client, "north", owner=email("o1"))
    south = await make_org(client, "south", owner=email("o2"))
    inv_id = (await invite(client, north, email("li"))).json()["id"]

    listed = (await client.get("/api/invitations", headers={"X-Tenant": south["slug"]})).json()
    assert listed["invitations"] == []
    r = await client.post(f"/api/invitations/{inv_id}/revoke", headers={"X-Tenant": south["slug"]})
    assert r.status_code == 404


async def test_data_plane_cannot_create_memberships_directly(client, app):
    org = await make_org(client, "north", owner=email("o"))
    owner_id = uuid.UUID(org["owner_user_id"])

    async with app.state.app_sessions() as session:
        await session.execute(select(func.set_config(TENANT_GUC, org["id"], True)))
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(
                text("INSERT INTO memberships (id, tenant_id, user_id, role) VALUES (:i, :t, :u, 'owner')"),
                {"i": uuid.uuid4(), "t": org["id"], "u": owner_id},
            )


# ---------------------------------------------------------- the last owner


async def test_the_last_owner_cannot_be_demoted_or_removed(client):
    org = await make_org(client, "north", owner=email("o"))
    owner_id = org["owner_user_id"]
    h = {"X-Tenant": org["slug"]}

    demote = await client.patch(f"/api/members/{owner_id}", json={"role": "admin"}, headers=h)
    remove = await client.delete(f"/api/members/{owner_id}", headers=h)
    assert demote.status_code == 409
    assert remove.status_code == 409
    assert demote.json()["detail"] == "an organization must keep at least one owner"


async def test_an_owner_can_step_down_once_another_owner_exists(client):
    org = await make_org(client, "north", owner=email("o"))
    h = {"X-Tenant": org["slug"]}
    token = (await invite(client, org, email("heir"), role="owner")).json()["token"]
    await accept(client, token, "Heir")

    r = await client.patch(f"/api/members/{org['owner_user_id']}", json={"role": "member"}, headers=h)
    assert r.status_code == 200
    assert sorted(m["role"] for m in await members(client, org)) == ["member", "owner"]


async def test_removing_a_member_keeps_the_invitation_history(client):
    org = await make_org(client, "north", owner=email("o"))
    h = {"X-Tenant": org["slug"]}
    joined = await accept(client, (await invite(client, org, email("li"))).json()["token"], "Li")

    r = await client.delete(f"/api/members/{joined.json()['user']['id']}", headers=h)
    assert r.status_code == 204
    invs = (await client.get("/api/invitations", headers=h)).json()["invitations"]
    assert invs[0]["status"] == "accepted"


async def test_concurrent_demotions_cannot_remove_both_owners(client, app):
    """Two owners each try to demote the other at the same moment.
    Exactly one wins; the organization keeps an owner."""
    org = await make_org(client, "north", owner=email("a"))
    token = (await invite(client, org, email("b"), role="owner")).json()["token"]
    b_id = uuid.UUID((await accept(client, token, "B")).json()["user"]["id"])
    a_id = uuid.UUID(org["owner_user_id"])

    async def pinned_session():
        s = app.state.app_sessions()
        await s.execute(select(func.set_config(TENANT_GUC, org["id"], True)))
        return s

    s1, s2 = await pinned_session(), await pinned_session()
    try:
        await change_membership(s1, a_id, "admin")  # holds the owner-row locks

        async def second():
            try:
                await change_membership(s2, b_id, "admin")
                await s2.commit()
                return "demoted"
            except LastOwnerError:
                await s2.rollback()
                return "refused"

        task = asyncio.create_task(second())
        await asyncio.sleep(0.3)
        assert not task.done()  # blocked on s1's row locks

        await s1.commit()
        assert await task == "refused"
    finally:
        await s1.close()
        await s2.close()

    roles = sorted(m["role"] for m in await members(client, org))
    assert roles == ["admin", "owner"]


async def test_preview_describes_the_invitation_without_consuming_it(client):
    org = await make_org(client, "north", owner=email("o"))
    who = email("li")
    token = (await invite(client, org, who, role="admin")).json()["token"]

    p = await client.post("/api/invitations/preview", json={"token": token})
    assert p.status_code == 200
    assert (p.json()["organization"], p.json()["email"], p.json()["role"], p.json()["status"]) == (
        "North", who, "admin", "pending"
    )
    assert "token" not in p.json()
    assert (await accept(client, token)).status_code == 200  # still usable
