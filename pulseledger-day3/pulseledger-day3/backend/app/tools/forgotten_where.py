"""
Run the query a tired engineer might write: `select(Customer)` with no
tenant filter, on the same restricted role the API uses.

    python -m app.tools.forgotten_where

Today it returns every tenant's customers, because the only thing keeping
tenants apart is the WHERE clause the application adds. That is the gap
Day 4 closes with Postgres row-level security.
"""
import asyncio

from sqlalchemy import select, text

from app.config import get_settings
from app.db import Customer, Tenant, build_engine


async def peek() -> list[tuple[str, str]]:
    engine = build_engine(get_settings().app_database_url)
    try:
        async with engine.connect() as conn:
            role = await conn.scalar(text("SELECT current_user"))
            rows = (
                await conn.execute(
                    # The forgotten clause: no customers_of(tenant) here.
                    select(Tenant.slug, Customer.email)
                    .join(Tenant, Tenant.id == Customer.tenant_id)
                    .order_by(Tenant.slug, Customer.email)
                )
            ).all()
        return role, [tuple(r) for r in rows]
    finally:
        await engine.dispose()


def main() -> None:
    role, rows = asyncio.run(peek())
    tenants = sorted({slug for slug, _ in rows})
    print(f"  Unscoped query as {role}: {len(rows)} rows from {len(tenants)} tenants")
    for slug, email in rows:
        print(f"    {slug:<20} {email}")
    print("  Nothing in the database stopped it.")


if __name__ == "__main__":
    main()
