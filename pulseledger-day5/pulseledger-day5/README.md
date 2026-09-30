# PulseLedger — Day 5: Org & Team Model

Part of *PulseLedger: 180 Days to Production-Grade Billing, Ledger & Agentic
Fintech Infrastructure*. Module 1 — Foundation.

Tenants become organizations with people in them. A **user** is one global
identity per email. A **membership** gives that user a role inside one
organization. An **invitation** is how a membership starts: a one-time token,
stored only as a hash, that expires, can be revoked, and can be used once.

## What changed since Day 4

| Area | Day 4 | Day 5 |
| --- | --- | --- |
| Tables | tenants, customers | + `users` (global), `memberships`, `invitations` |
| RLS | customers | + memberships, invitations (tenant policy), users (visible only if a member of the current tenant) |
| Tenant creation | slug + name | optional `owner` in the same transaction; `POST /api/tenants/{slug}/owner` for ownerless orgs |
| New endpoints | | `/api/members` (GET, PATCH, DELETE), `/api/invitations` (POST, GET), `/invitations/{id}/revoke`, `/invitations/preview`, `/invitations/accept` |
| Invariants | | one pending invite per email per org; one-time tokens; an org never loses its last owner (row-locked, race-tested) |
| Frontend | customers + isolation | + Team panel (members, invitations, invite form), `/invite` accept page |
| Tests | 34 | 56 |

Upgrading from Day 4 is in place. Organizations created on Day 3/4 have no
members; `demo.sh` gives each one an owner through the claim endpoint.

## Changed and new files

```
backend/app/db.py            User, Membership, Invitation; RLS for the new tables; grants
backend/app/team.py          new: members, invitations, accept, preview, last-owner guard
backend/app/routes.py        tenant creation takes an optional first owner
backend/app/main.py          registers the team router; CORS allows DELETE
backend/app/tools/rls_drill.py   step 1 now checks every protected table
tests/test_team.py           new (22 tests)
frontend/app/components/TeamPanel.tsx   new
frontend/app/invite/page.tsx            new
frontend/app/page.tsx        mounts the Team panel
scripts/_demo.py, demo.sh
```

## Who can do what (and what's missing)

| Operation | Plane | Why |
| --- | --- | --- |
| Create org + first owner, claim owner | control (owner connection) | creates identity across the tenant boundary |
| Accept / preview an invitation | control | the token holder isn't a member yet |
| List members, invite, revoke, change role, remove | data (`pulseledger_app` + RLS) | stays inside one tenant |

The data-plane role cannot `INSERT` into `memberships` or write to `users` at
all; memberships only come from the control plane.

**Not yet:** requests aren't authenticated, so anyone who can send
`X-Tenant` can invite people. Authentication arrives on Day 6 (JWT) and
role-based permissions on Day 7.

## Commands

```bash
./scripts/build.sh                 # or USE_DOCKER=true ./scripts/build.sh
./scripts/run.sh                   # backend :8005, frontend :4005
./scripts/test.sh                  # 56 passed
./scripts/verify.sh
./scripts/demo.sh                  # prints an /invite link to open in the browser
./scripts/cleanup.sh               # PURGE=true drops the Postgres volume (Docker)
```

Every script accepts `USE_DOCKER=true`. Native runs need Python 3.13, Node 22,
Postgres 15+ (17 in Compose; `ON DELETE SET NULL (column)` needs 15+) with
pgvector, and Redis 7 on `127.0.0.1:5432` / `:6379`. The owner connection
must be able to create roles and databases.

## Versions

- Python 3.13, FastAPI 0.141.1, SQLAlchemy 2.0.54, asyncpg 0.31.0,
  redis-py 8.1.0, pydantic-settings 2.15.0
- Node 22, Next.js 16.3.6, React 19.2.8, Tailwind CSS 4.3.3
- Images: `pgvector/pgvector:pg17`, `redis:7-alpine`, `python:3.13-slim`, `node:22-slim`
