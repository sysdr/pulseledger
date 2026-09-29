# PulseLedger — Day 4: Row-Level Tenancy

Part of *PulseLedger: 180 Days to Production-Grade Billing, Ledger & Agentic
Fintech Infrastructure*. Module 1 — Foundation.

Day 3 isolated tenants with a `WHERE tenant_id = …` in application code, and
ended by showing an unscoped query reading every tenant's rows. Day 4 moves
the rule into Postgres with row-level security (RLS). The same query now
returns zero rows, and writes that would cross tenants are refused by the
database.

## What changed since Day 3

| Area | Day 3 | Day 4 |
| --- | --- | --- |
| Isolation guard | `customers_of()` WHERE clause | Postgres RLS policy `tenant_isolation` (WHERE clause kept as a second layer) |
| Per-request DB state | none | `app.tenant_id`, set with `set_config(..., is_local => true)` per transaction |
| Unscoped query, no tenant | every tenant's rows | 0 rows |
| Cross-tenant insert / update | allowed by the database | refused: `new row violates row-level security policy` |
| Readiness | Postgres, Redis, app role | + `isolation` (RLS on and forced, no bypass, 0 rows without a tenant) |
| Tests | 26 | 34 (new `tests/test_rls.py` attacks the policy directly) |
| Demo tool | `forgotten_where` | `rls_drill` (five attempts to cross tenants) |

Upgrading from Day 3 is in place: the backend enables RLS on the existing
`customers` table at boot. Your Day 3 tenants and customers keep working.

## Changed files

```
backend/app/db.py            TENANT_GUC, TENANT_PREDICATE, apply_tenant_isolation()
backend/app/tenancy.py       tenant_session() pins each transaction to one tenant
backend/app/probes.py        probe_isolation()
backend/app/main.py          isolation is required at boot
backend/app/tools/rls_drill.py   (replaces forgotten_where.py)
tests/test_rls.py            new
tests/test_tenancy.py        the Day 3 "gap" test is flipped
frontend/app/page.tsx        isolation panel
scripts/demo.sh, _demo.py, _report.py
```

## Commands

```bash
./scripts/build.sh                 # or USE_DOCKER=true ./scripts/build.sh
./scripts/run.sh                   # backend :8004, frontend :4004
./scripts/test.sh                  # 34 passed
./scripts/verify.sh
./scripts/demo.sh
./scripts/cleanup.sh               # stop apps/Compose, scrub secrets, drop local artifacts; PURGE=true also drops volumes
```

Every script accepts `USE_DOCKER=true`. Native runs need Python 3.13, Node 22,
Postgres 17 (pgvector available) and Redis 7 on `127.0.0.1:5432` / `:6379`
(`docker compose up -d postgres redis` gives you just those two). The owner
connection must be able to create roles and databases; the Compose user can.

## Things RLS does not cover

- **Superusers and `BYPASSRLS` roles skip policies.** The owner connection
  in this dev setup is a superuser, which is why the control plane can still
  count customers per tenant. Tenant traffic never uses it.
- **Constraint checks ignore policies.** A unique constraint sees every
  row. That's why Day 3 made email unique per tenant: a global one would let
  a 409 reveal another tenant's customer.
- **Session-level settings leak through connection pools.** Always
  `set_config(..., true)` (transaction-local), never plain `SET`.
  `tests/test_rls.py` demonstrates both.

## Versions

- Python 3.13, FastAPI 0.141.1, SQLAlchemy 2.0.54, asyncpg 0.31.0,
  redis-py 8.1.0, pydantic-settings 2.15.0
- Node 22, Next.js 16.3.6, React 19.2.8, Tailwind CSS 4.3.3
- Images: `pgvector/pgvector:pg17`, `redis:7-alpine`, `python:3.13-slim`, `node:22-slim`
