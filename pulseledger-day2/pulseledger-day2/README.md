# PulseLedger — Day 2: Dev Environment

Part of *PulseLedger: 180 Days to Production-Grade Billing, Ledger & Agentic
Fintech Infrastructure*. Module 1 — Foundation.

Day 1 gave us a backend that could say "I'm alive." Day 2 connects it to
Postgres 17 (with pgvector) and Redis 7, wires the whole stack into Docker
Compose, and teaches the service the difference between *alive* and *ready*.

## What changed since Day 1

| Area | Day 1 | Day 2 |
| --- | --- | --- |
| Backend endpoints | `/api/health` | `/api/health` (liveness), `/api/ready` (readiness), `/api/boots` |
| Data services | none | Postgres 17 + pgvector, Redis 7 |
| Config | hard-coded | `pydantic-settings`, `.env`, live Stripe keys refused at boot |
| Lifecycle | implicit | explicit `starting → ready ⇄ degraded → stopping` state machine |
| Frontend | inline styles, health dot | Tailwind v4, live readiness + boot history, polls every 3 s |
| Docker | backend + frontend | 4 services, healthchecks, `depends_on: service_healthy` |
| Tests | 1 | 13, against real Postgres and Redis |

## Layout

```
backend/app/
  config.py      typed settings + Stripe test-mode guard
  lifecycle.py   service state machine
  db.py          async engine factory, service_boots table, schema bootstrap
  probes.py      real Postgres/pgvector and Redis probes
  main.py        app factory, lifespan, routes
frontend/app/    Next.js App Router page (Tailwind v4)
tests/           pytest-asyncio + httpx ASGITransport, no mocks
scripts/         build, run, test, verify, demo, cleanup
docker-compose.yml
```

## Prerequisites

- **Docker path:** Docker with Compose v2. Nothing else.
- **Native path:** Python 3.13, Node 22, and Postgres 17 (with the pgvector
  extension available) plus Redis 7 reachable on `127.0.0.1:5432` / `:6379`.
  The quickest way to get just the data services is
  `docker compose up -d postgres redis`.

The database user needs permission to run `CREATE EXTENSION vector` (the
Compose user does). Credentials default to `pulseledger / pulseledger`,
database `pulseledger`; override in `.env` (see `.env.example`).

## Commands

```bash
./scripts/build.sh                 # or USE_DOCKER=true ./scripts/build.sh
./scripts/run.sh                   # backend :8002, frontend :4002
./scripts/test.sh                  # 13 passed
./scripts/verify.sh                # liveness, then readiness
./scripts/demo.sh                  # outage drill runs with USE_DOCKER=true,
                                   # or natively with DEMO_OUTAGE=true
./scripts/cleanup.sh               # stop app + containers, prune Docker, delete
                                   # build artifacts; PURGE=true also drops volumes
```

Every script accepts `USE_DOCKER=true`.

## Stripe

Nothing calls Stripe yet. The key guard is live today: if `STRIPE_SECRET_KEY`
is set, it must start with `sk_test_` or `rk_test_`. A live key
(`sk_live_` / `rk_live_`) stops the backend from starting.

## Versions

- Python 3.13, FastAPI 0.141.1, SQLAlchemy 2.0.54 (asyncio), asyncpg 0.31.0,
  redis-py 8.1.0, pydantic-settings 2.15.0
- Node 22, Next.js 16.3.6, React 19.2.8, Tailwind CSS 4.3.3
- Images: `pgvector/pgvector:pg17`, `redis:7-alpine`, `python:3.13-slim`,
  `node:22-slim`

Next.js moved from 16.2.x to 16.3.6: `npm audit` flags every release up to
16.3.2 with critical advisories (GHSA-p293-qw3h-jr36, GHSA-2xp9-vwfh-vxw4).
16.3.6 audits clean.
