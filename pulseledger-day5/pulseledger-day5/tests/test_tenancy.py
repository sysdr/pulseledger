"""
The Day 4 tenant model, tested against the real database with the real
restricted role. Each test creates its own uniquely named tenants, so the
suite can run repeatedly against the same database.
"""
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import Customer


def slug(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


async def make_tenant(client, label: str) -> dict:
    r = await client.post("/api/tenants", json={"slug": slug(label), "name": label.title()})
    assert r.status_code == 201, r.text
    return r.json()


async def add_customer(client, tenant_slug: str, email: str, name: str = "Ana Ruiz"):
    return await client.post(
        "/api/customers",
        json={"email": email, "name": name},
        headers={"X-Tenant": tenant_slug},
    )


async def test_customer_is_created_inside_its_tenant(client):
    t = await make_tenant(client, "northwind")
    r = await add_customer(client, t["slug"], "ana@example.com")

    assert r.status_code == 201
    assert r.json()["tenant_id"] == t["id"]

    listed = (await client.get("/api/customers", headers={"X-Tenant": t["slug"]})).json()
    assert [c["email"] for c in listed["customers"]] == ["ana@example.com"]


async def test_tenants_cannot_see_each_others_customers(client):
    a = await make_tenant(client, "alpha")
    b = await make_tenant(client, "beta")
    await add_customer(client, a["slug"], "only-a@example.com")

    listed_b = (await client.get("/api/customers", headers={"X-Tenant": b["slug"]})).json()
    assert listed_b["customers"] == []


async def test_direct_id_lookup_across_tenants_is_404(client):
    a = await make_tenant(client, "alpha")
    b = await make_tenant(client, "beta")
    cid = (await add_customer(client, a["slug"], "ana@example.com")).json()["id"]

    assert (await client.get(f"/api/customers/{cid}", headers={"X-Tenant": a["slug"]})).status_code == 200
    assert (await client.get(f"/api/customers/{cid}", headers={"X-Tenant": b["slug"]})).status_code == 404


async def test_same_email_allowed_in_different_tenants_but_not_twice_in_one(client):
    a = await make_tenant(client, "alpha")
    b = await make_tenant(client, "beta")

    assert (await add_customer(client, a["slug"], "shared@example.com")).status_code == 201
    assert (await add_customer(client, b["slug"], "shared@example.com")).status_code == 201
    assert (await add_customer(client, a["slug"], "SHARED@example.com")).status_code == 409


async def test_data_plane_role_cannot_change_the_tenant_registry(client, app):
    t = await make_tenant(client, "gamma")

    async with app.state.app_sessions() as session:
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(
                text("UPDATE tenants SET status = 'closed' WHERE slug = :s"), {"s": t["slug"]}
            )


async def test_app_role_is_not_a_superuser(client, app):
    async with app.state.app_engine.connect() as conn:
        is_super = await conn.scalar(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        )
    assert is_super is False


async def test_unscoped_query_sees_nothing_without_a_tenant(client, app):
    """Day 3 documented this gap: an unscoped query saw every tenant.
    Since Day 4, Postgres returns zero rows instead."""
    a = await make_tenant(client, "alpha")
    await add_customer(client, a["slug"], "a@example.com")

    async with app.state.app_sessions() as session:
        tenant_ids = (await session.scalars(select(Customer.tenant_id))).all()

    assert tenant_ids == []


async def test_missing_and_unknown_tenant_headers(client):
    assert (await client.get("/api/customers")).status_code == 400
    r = await client.get("/api/customers", headers={"X-Tenant": "no-such-tenant"})
    assert r.status_code == 404


async def test_suspended_tenant_is_read_only_until_reactivated(client):
    t = await make_tenant(client, "delta")
    await add_customer(client, t["slug"], "before@example.com")

    r = await client.patch(f"/api/tenants/{t['slug']}/status", json={"status": "suspended"})
    assert r.json()["status"] == "suspended"

    headers = {"X-Tenant": t["slug"]}
    assert (await client.get("/api/customers", headers=headers)).status_code == 200
    assert (await add_customer(client, t["slug"], "during@example.com")).status_code == 403

    await client.patch(f"/api/tenants/{t['slug']}/status", json={"status": "active"})
    assert (await add_customer(client, t["slug"], "after@example.com")).status_code == 201


async def test_closed_is_terminal_and_hides_the_tenant(client):
    t = await make_tenant(client, "omega")
    assert (await client.patch(f"/api/tenants/{t['slug']}/status", json={"status": "closed"})).status_code == 200

    r = await client.patch(f"/api/tenants/{t['slug']}/status", json={"status": "active"})
    assert r.status_code == 409
    assert (await client.get("/api/customers", headers={"X-Tenant": t["slug"]})).status_code == 404


async def test_duplicate_tenant_slug_is_rejected(client):
    t = await make_tenant(client, "echo")
    r = await client.post("/api/tenants", json={"slug": t["slug"], "name": "Again"})
    assert r.status_code == 409


async def test_tenant_list_counts_customers_per_tenant(client):
    t = await make_tenant(client, "count")
    await add_customer(client, t["slug"], "one@example.com")
    await add_customer(client, t["slug"], "two@example.com")

    tenants = (await client.get("/api/tenants")).json()["tenants"]
    mine = next(x for x in tenants if x["slug"] == t["slug"])
    assert mine["customer_count"] == 2
    assert mine["allowed_next"] == ["closed", "suspended"]


async def test_readiness_checks_the_data_plane_role(client):
    role = (await client.get("/api/ready")).json()["dependencies"]["app_role"]

    assert role["ok"] is True
    assert role["details"]["role"] == "pulseledger_app"
    assert role["details"]["can_update_tenants"] is False
