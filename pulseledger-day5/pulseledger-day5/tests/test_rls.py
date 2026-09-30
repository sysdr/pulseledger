"""
Row-level security, attacked directly. These tests skip the API and talk to
Postgres as the restricted data-plane role, the way a buggy query, a
support script, or a compromised code path would.
"""
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.db import RLS_TABLES, TENANT_GUC, Customer


async def two_tenants_with_customers(client) -> tuple[dict, dict]:
    tenants = []
    for label in ("north", "south"):
        r = await client.post(
            "/api/tenants", json={"slug": f"{label}-{uuid.uuid4().hex[:8]}", "name": label.title()}
        )
        t = r.json()
        for i in range(2):
            await client.post(
                "/api/customers",
                json={"email": f"c{i}@{label}.example", "name": f"Customer {i}"},
                headers={"X-Tenant": t["slug"]},
            )
        tenants.append(t)
    return tenants[0], tenants[1]


async def declare(session, tenant_id: str) -> None:
    await session.execute(select(func.set_config(TENANT_GUC, tenant_id, True)))


async def test_declared_tenant_sees_only_its_rows_without_any_where_clause(client, app):
    north, _ = await two_tenants_with_customers(client)

    async with app.state.app_sessions() as session:
        await declare(session, north["id"])
        owners = set((await session.scalars(select(Customer.tenant_id))).all())

    assert owners == {uuid.UUID(north["id"])}


async def test_insert_for_another_tenant_is_refused(client, app):
    north, south = await two_tenants_with_customers(client)

    async with app.state.app_sessions() as session:
        await declare(session, north["id"])
        session.add(Customer(tenant_id=uuid.UUID(south["id"]), email="x@x.example", name="X"))
        with pytest.raises(DBAPIError, match="violates row-level security policy"):
            await session.flush()


async def test_moving_a_row_to_another_tenant_is_refused(client, app):
    north, south = await two_tenants_with_customers(client)

    async with app.state.app_sessions() as session:
        await declare(session, north["id"])
        with pytest.raises(DBAPIError, match="violates row-level security policy"):
            await session.execute(
                text("UPDATE customers SET tenant_id = :s WHERE tenant_id = :n"),
                {"s": south["id"], "n": north["id"]},
            )


async def test_another_tenants_rows_cannot_be_updated_or_deleted(client, app):
    north, south = await two_tenants_with_customers(client)

    async with app.state.app_sessions() as session:
        await declare(session, north["id"])
        updated = await session.execute(
            text("UPDATE customers SET name = 'hijacked' WHERE tenant_id = :s"), {"s": south["id"]}
        )
        deleted = await session.execute(
            text("DELETE FROM customers WHERE tenant_id = :s"), {"s": south["id"]}
        )
        await session.commit()

    # Invisible rows can't be matched, so nothing is touched. No error either.
    assert updated.rowcount == 0
    assert deleted.rowcount == 0
    listed = await client.get("/api/customers", headers={"X-Tenant": south["slug"]})
    assert {c["name"] for c in listed.json()["customers"]} == {"Customer 0", "Customer 1"}


async def test_tenant_setting_does_not_leak_to_the_next_transaction(client, app):
    north, _ = await two_tenants_with_customers(client)

    async with app.state.app_engine.connect() as conn:
        await conn.execute(select(func.set_config(TENANT_GUC, north["id"], True)))
        assert await conn.scalar(select(func.count()).select_from(Customer)) == 2
        await conn.commit()

        # Same physical connection, new transaction, nothing declared.
        leftover = await conn.scalar(text(f"SELECT current_setting('{TENANT_GUC}', true)"))
        visible = await conn.scalar(select(func.count()).select_from(Customer))

    assert leftover == ""  # not NULL: the reason the policy needs NULLIF
    assert visible == 0


async def test_session_level_setting_would_leak(client, app):
    """Why the code uses is_local => true. A session-level SET survives the
    transaction and follows the pooled connection to the next request."""
    north, _ = await two_tenants_with_customers(client)

    async with app.state.app_engine.connect() as conn:
        await conn.execute(select(func.set_config(TENANT_GUC, north["id"], False)))
        await conn.commit()
        still_visible = await conn.scalar(select(func.count()).select_from(Customer))
        await conn.execute(text(f"RESET {TENANT_GUC}"))
        await conn.commit()

    assert still_visible == 2


async def test_every_tenant_table_has_rls_enabled_and_forced(app):
    async with app.state.engine.connect() as conn:
        for table in RLS_TABLES:
            enabled, forced = (
                await conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE oid = CAST(:t AS regclass)"
                    ),
                    {"t": table},
                )
            ).one()
            assert (enabled, forced) == (True, True), table


async def test_readiness_proves_isolation(client):
    iso = (await client.get("/api/ready")).json()["dependencies"]["isolation"]

    assert iso["ok"] is True
    assert iso["details"]["bypass_rls"] is False
    assert iso["details"]["tables"]["customers"]["visible_without_tenant"] == 0
