"""
PulseLedger — Day 1: Kickoff & scaffolding

Backend entrypoint. Today's only job: prove the service is alive and
report which day of the course produced it.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="PulseLedger API",
    description="Subscription billing, ledger, and marketplace payouts platform — built one lesson at a time.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4001"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    """Liveness check. Every future lesson's verify.sh polls this first."""
    return {"status": "ok", "day": 1, "service": "pulseledger-backend"}
