#!/usr/bin/env bash
# PulseLedger Day 4 — demo.sh
# 1-6) the tenant model through the API, now isolated by Postgres RLS
# 7)   RLS drill: five direct attempts to cross tenants, as the data-plane role
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

BASE="http://127.0.0.1:$BACKEND_PORT"

echo "=== PulseLedger Day 4 Demo: row-level tenancy ==="
echo "Keep http://localhost:$FRONTEND_PORT open; it refreshes every 3 seconds."

python3 "$ROOT_DIR/scripts/_demo.py" "$BASE"

echo ""
echo "7. RLS drill: trying to cross tenants directly in Postgres"
if [ "${USE_DOCKER:-false}" = "true" ]; then
  "${COMPOSE[@]}" exec -T backend python -m app.tools.rls_drill
else
  (cd "$ROOT_DIR" && PYTHONPATH=backend "$ROOT_DIR/.venv/bin/python" -m app.tools.rls_drill)
fi

echo ""
echo "=== Demo complete ==="
