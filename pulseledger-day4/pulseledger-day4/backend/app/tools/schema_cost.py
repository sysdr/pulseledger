"""
Measure, on your own Postgres, what schema-per-tenant costs compared with a
shared table plus a tenant_id column.

    python -m app.tools.schema_cost            # 200 tenants
    python -m app.tools.schema_cost --tenants 500

It creates real schemas and tables in scratch namespaces (prefixed
`pl_costdemo_`), runs a real "migration" (ADD COLUMN) against each layout,
reports catalog growth and timings, and drops everything it created.
Numbers depend on your hardware; the shape of the result does not.
"""
import argparse
import asyncio
import time

from sqlalchemy import text

from app.config import get_settings
from app.db import build_engine

PREFIX = "pl_costdemo_"

CUSTOMERS_DDL = """
CREATE TABLE {schema}.customers (
    id uuid PRIMARY KEY,
    {tenant_col}
    email varchar(254) NOT NULL,
    name varchar(120) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE ({unique_cols})
)
"""


async def _relations(conn) -> int:
    return await conn.scalar(text("SELECT count(*) FROM pg_class"))


async def _drop_leftovers(conn) -> None:
    schemas = (
        await conn.scalars(
            text("SELECT nspname FROM pg_namespace WHERE nspname LIKE :p"),
            {"p": f"{PREFIX}%"},
        )
    ).all()
    for s in schemas:
        await conn.execute(text(f"DROP SCHEMA {s} CASCADE"))


async def measure(tenants: int) -> dict:
    engine = build_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            await _drop_leftovers(conn)

        # ---- schema per tenant
        async with engine.begin() as conn:
            before = await _relations(conn)
            t0 = time.perf_counter()
            for i in range(tenants):
                schema = f"{PREFIX}t{i:05d}"
                await conn.execute(text(f"CREATE SCHEMA {schema}"))
                await conn.execute(
                    text(CUSTOMERS_DDL.format(schema=schema, tenant_col="", unique_cols="email"))
                )
            create_s = time.perf_counter() - t0
            per_tenant_rel = await _relations(conn) - before

        async with engine.begin() as conn:
            t0 = time.perf_counter()
            for i in range(tenants):
                await conn.execute(
                    text(f"ALTER TABLE {PREFIX}t{i:05d}.customers ADD COLUMN phone varchar(32)")
                )
            per_tenant_migrate_s = time.perf_counter() - t0

        # ---- shared table, row-level isolation
        async with engine.begin() as conn:
            before = await _relations(conn)
            schema = f"{PREFIX}shared"
            await conn.execute(text(f"CREATE SCHEMA {schema}"))
            await conn.execute(
                text(
                    CUSTOMERS_DDL.format(
                        schema=schema,
                        tenant_col="tenant_id uuid NOT NULL,",
                        unique_cols="tenant_id, email",
                    )
                )
            )
            shared_rel = await _relations(conn) - before

        async with engine.begin() as conn:
            t0 = time.perf_counter()
            await conn.execute(
                text(f"ALTER TABLE {PREFIX}shared.customers ADD COLUMN phone varchar(32)")
            )
            shared_migrate_s = time.perf_counter() - t0

        return {
            "tenants": tenants,
            "schema_per_tenant": {
                "relations_added": per_tenant_rel,
                "ddl_statements_per_migration": tenants,
                "create_ms": round(create_s * 1000, 1),
                "migration_ms": round(per_tenant_migrate_s * 1000, 1),
            },
            "shared_table": {
                "relations_added": shared_rel,
                "ddl_statements_per_migration": 1,
                "create_ms": None,
                "migration_ms": round(shared_migrate_s * 1000, 1),
            },
        }
    finally:
        async with engine.begin() as conn:
            await _drop_leftovers(conn)
        await engine.dispose()


def _print(r: dict) -> None:
    a, b = r["schema_per_tenant"], r["shared_table"]
    print(f"  {r['tenants']} tenants, one customers table each vs. one shared table")
    print()
    print(f"  {'':34}{'schema-per-tenant':>20}{'shared table':>16}")
    print(f"  {'relations added to pg_class':34}{a['relations_added']:>20}{b['relations_added']:>16}")
    print(f"  {'DDL statements per migration':34}{a['ddl_statements_per_migration']:>20}{b['ddl_statements_per_migration']:>16}")
    print(f"  {'time to run one migration (ms)':34}{a['migration_ms']:>20}{b['migration_ms']:>16}")
    print()
    print("  Scratch schemas dropped.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--tenants", type=int, default=200)
    args = parser.parse_args()
    _print(asyncio.run(measure(max(1, min(args.tenants, 1000)))))


if __name__ == "__main__":
    main()
