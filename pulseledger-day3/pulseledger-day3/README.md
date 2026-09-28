# PulseLedger — Day 3: Multi-Tenant Data Model

Part of *PulseLedger: 180 Days to Production-Grade Billing, Ledger & Agentic
Fintech Infrastructure*. Module 1 — Foundation.

Day 3 decides how tenants share one database, and builds it: a tenant
registry, the first tenant-owned table, a restricted data-plane role, and a
tenant lifecycle. It also measures, on your own Postgres, what the
schema-per-tenant alternative would cost.

## What changed since Day 2

| Area | Day 2 | Day 3 |
| --- | --- | --- |
| Tables | `service_boots` | + `tenants` (registry), `customers` (tenant-owned) |
| DB roles | one owner connection | owner (control plane) + `pulseledger_app` (data plane, least privilege) |
| Endpoints | health, ready, boots | + `/api/tenants`, `/api/tenants/{slug}/status`, `/api/customers` |
| Tenant scoping | none | `X-Tenant` header, every customer query built by `customers_of(tenant)` |
| Readiness | Postgres, Redis | + `app_role` check (not superuser, can't edit tenants) |
| Tests | 13 | 26, on a separate `<db>_test` database |
| Tools | none | `app.tools.schema_cost`, `app.tools.forgotten_where` |

## Layout

```
backend/app/
  config.py              settings; adds APP_DATABASE_URL
  db.py                  Tenant, Customer models; bootstrap creates the app role
  tenancy.py             tenant resolution, lifecycle rules, customers_of()
  routes.py              control-plane + data-plane routes
  probes.py              Postgres, Redis, app-role readiness probes
  main.py                app factory, two engines, lifespan
  tools/schema_cost.py   schema-per-tenant vs shared table, measured
  tools/forgotten_where.py  what an unscoped query sees today
frontend/app/page.tsx    tenant switcher, customers, add-customer form
tests/                   pytest-asyncio + httpx ASGITransport, no mocks
```

## Commands

```bash
./scripts/build.sh                 # or USE_DOCKER=true ./scripts/build.sh
./scripts/run.sh                   # backend :8003, frontend :4003
./scripts/test.sh                  # 26 passed
./scripts/verify.sh
./scripts/demo.sh                  # TENANTS=500 ./scripts/demo.sh for a bigger cost run
./scripts/cleanup.sh               # PURGE=true drops the Postgres volume (Docker)
```

Every script accepts `USE_DOCKER=true`. Native runs need Python 3.13,
Node 22, and Postgres 17 (pgvector available) plus Redis 7 on
`127.0.0.1:5432` / `:6379`; `docker compose up -d postgres redis` gives you
just those two.

The owner connection (`DATABASE_URL`) must be allowed to create roles; the
Compose user is. The backend creates `pulseledger_app` at boot using the
credentials in `APP_DATABASE_URL`. Tests create and use
`<database>_test`, so test tenants never appear in the app.

## A known gap, on purpose

Isolation today is the `WHERE tenant_id = …` that `customers_of()` adds.
`demo.sh` step 7 runs a query without it, as the same restricted role, and
gets every tenant's rows. Day 4 moves the rule into Postgres with
row-level security.

## Versions

- Python 3.13, FastAPI 0.141.1, SQLAlchemy 2.0.54, asyncpg 0.31.0,
  redis-py 8.1.0, pydantic-settings 2.15.0
- Node 22, Next.js 16.3.6, React 19.2.8, Tailwind CSS 4.3.3
- Images: `pgvector/pgvector:pg17`, `redis:7-alpine`, `python:3.13-slim`, `node:22-slim`
