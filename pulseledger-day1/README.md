# PulseLedger — Day 1: Kickoff & Scaffolding

Part of *PulseLedger: 180 Days to Production-Grade Billing, Ledger & Agentic
Fintech Infrastructure*. Module 1 — Foundation.

## What's here

- `backend/` — FastAPI service with a single `/api/health` endpoint
- `frontend/` — Next.js 16 (App Router) page that fetches and displays that
  health status live
- `tests/` — pytest-asyncio test using `ASGITransport` (no running server
  required)
- `scripts/` — build, run, test, verify, demo, cleanup

## Quick start

```bash
./scripts/build.sh      # or: USE_DOCKER=true ./scripts/build.sh
./scripts/run.sh
./scripts/verify.sh
./scripts/demo.sh
./scripts/cleanup.sh
```

Backend: http://localhost:8001
Frontend: http://localhost:4001

## Versions

- Python 3.12, FastAPI 0.118.0
- Node 22, Next.js 16.2.11, React 19.2.1

Next.js and React are pinned to versions patched against the December 2025
React Server Components vulnerabilities (CVE-2025-66478, CVE-2025-55182,
CVE-2025-55183, CVE-2025-55184). Do not downgrade below these without
checking current advisories.
