"""
Try to break tenant isolation, as the same restricted role the API uses.

    python -m app.tools.rls_drill
    python -m app.tools.rls_drill --tenant northwind-traders --other brightpath-labs

Five attempts, each in its own transaction and rolled back, so the drill
never changes data. Attempts 2 and 4 first insert their own legitimate row
for the declared tenant, so the drill proves something even on an empty
database:

  1. The forgotten WHERE clause, with no tenant declared, on every
     protected table (customers, memberships, invitations, users).
  2. The same unscoped query with a tenant declared.
  3. Insert a row for another tenant while declared as this one.
  4. Move one of this tenant's rows to another tenant.
  5. Reuse the same pooled connection after a tenant's transaction ended.
"""
import argparse
import asyncio

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.config import get_settings
from app.db import RLS_TABLES, TENANT_GUC, Customer, Tenant, build_engine


async def _plant_own_row(conn, tenant_id) -> None:
    """A legitimate row for the declared tenant, inside the current transaction."""
    await conn.execute(
        Customer.__table__.insert().values(
            tenant_id=tenant_id, email="drill-own@drill.example", name="Drill"
        )
    )


def _pg_error(exc: DBAPIError) -> str:
    return str(exc.orig).splitlines()[0].split(": ", 1)[-1]


async def drill(tenant_slug: str, other_slug: str) -> None:
    engine = build_engine(get_settings().app_database_url)
    try:
        async with engine.connect() as conn:
            role = await conn.scalar(text("SELECT current_user"))
            ids = dict(
                (await conn.execute(
                    select(Tenant.slug, Tenant.id).where(Tenant.slug.in_([tenant_slug, other_slug]))
                )).all()
            )
            if tenant_slug not in ids or other_slug not in ids:
                raise SystemExit(f"  tenants {tenant_slug!r} and {other_slug!r} must exist first")
            me, other = ids[tenant_slug], ids[other_slug]
            await conn.rollback()

            print(f"  Connected as {role}. Every attempt below is rolled back.\n")

            # 1. No tenant declared: the forgotten WHERE clause from Day 3.
            counts = []
            for table in RLS_TABLES:
                counts.append(f"{table} {await conn.scalar(text(f'SELECT count(*) FROM {table}'))}")
            print(f"  1. unscoped SELECT, no tenant declared      -> {', '.join(counts)}")
            await conn.rollback()

            # 2. Tenant declared, still no WHERE clause in the query.
            await conn.execute(select(func.set_config(TENANT_GUC, str(me), True)))
            await _plant_own_row(conn, me)
            rows = (await conn.execute(select(Customer.tenant_id))).scalars().all()
            print(f"  2. unscoped SELECT, tenant declared         -> {len(rows)} row{'s' if len(rows) != 1 else ''}, "
                  f"all belong to {tenant_slug}: {all(t == me for t in rows)}")
            await conn.rollback()

            # 3. Insert a row that claims to belong to someone else.
            await conn.execute(select(func.set_config(TENANT_GUC, str(me), True)))
            try:
                await conn.execute(
                    Customer.__table__.insert().values(
                        tenant_id=other, email="planted@drill.example", name="Planted"
                    )
                )
                print("  3. INSERT for another tenant                 -> ALLOWED (isolation broken)")
            except DBAPIError as exc:
                print(f"  3. INSERT for another tenant                 -> refused: {_pg_error(exc)}")
            await conn.rollback()

            # 4. Hand one of our rows over to another tenant.
            await conn.execute(select(func.set_config(TENANT_GUC, str(me), True)))
            await _plant_own_row(conn, me)
            try:
                moved = await conn.execute(
                    text("UPDATE customers SET tenant_id = :other WHERE tenant_id = :me"),
                    {"other": other, "me": me},
                )
                print(f"  4. UPDATE row to another tenant              -> ALLOWED ({moved.rowcount} rows)")
            except DBAPIError as exc:
                print(f"  4. UPDATE row to another tenant              -> refused: {_pg_error(exc)}")
            await conn.rollback()

            # 5. Same pooled connection, next transaction, nothing declared.
            await conn.execute(select(func.set_config(TENANT_GUC, str(me), True)))
            await conn.commit()
            leftover = await conn.scalar(text(f"SELECT current_setting('{TENANT_GUC}', true)"))
            n = await conn.scalar(select(func.count()).select_from(Customer))
            print(f"  5. same connection, next transaction         -> setting is {leftover!r}, {n} rows")
            await conn.rollback()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Try to break tenant isolation.")
    parser.add_argument("--tenant", default="northwind-traders")
    parser.add_argument("--other", default="brightpath-labs")
    args = parser.parse_args()
    asyncio.run(drill(args.tenant, args.other))


if __name__ == "__main__":
    main()
