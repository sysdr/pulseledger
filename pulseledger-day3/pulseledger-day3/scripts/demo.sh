#!/usr/bin/env bash
# PulseLedger Day 3 — demo.sh
# 1-6) tenant model, live against the running backend
# 7)   forgotten-WHERE peek  8) schema-per-tenant vs. shared-table cost, measured on your Postgres
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

BASE="http://127.0.0.1:$BACKEND_PORT"

echo "=== PulseLedger Day 3 Demo: multi-tenant data model ==="
echo "Keep http://localhost:$FRONTEND_PORT open; it refreshes every 3 seconds."

python3 "$ROOT_DIR/scripts/_demo.py" "$BASE"

echo ""
echo "7. The forgotten WHERE clause (same restricted role the API uses)"
if [ "${USE_DOCKER:-false}" = "true" ]; then
  "${COMPOSE[@]}" exec -T backend python -m app.tools.forgotten_where
else
  (cd "$ROOT_DIR" && PYTHONPATH=backend "$ROOT_DIR/.venv/bin/python" -m app.tools.forgotten_where)
fi

echo ""
echo "8. What the other design would cost (measured now, then cleaned up)"
if [ "${USE_DOCKER:-false}" = "true" ]; then
  "${COMPOSE[@]}" exec -T backend python -m app.tools.schema_cost --tenants "${TENANTS:-200}"
else
  (cd "$ROOT_DIR" && PYTHONPATH=backend "$ROOT_DIR/.venv/bin/python" -m app.tools.schema_cost --tenants "${TENANTS:-200}")
fi

echo ""
echo "=== Demo complete ==="
