#!/usr/bin/env bash
# PulseLedger Day 5 — demo.sh
# 1-7) organizations, invitations, memberships through the API
# 8)   RLS drill across every protected table, including the new ones
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

BASE="http://127.0.0.1:$BACKEND_PORT"

echo "=== PulseLedger Day 5 Demo: organizations, members, invitations ==="
echo "Keep http://localhost:$FRONTEND_PORT open; it refreshes every 3 seconds."

python3 "$ROOT_DIR/scripts/_demo.py" "$BASE" "http://localhost:$FRONTEND_PORT"

echo ""
echo "8. RLS drill: trying to cross tenants directly in Postgres"
if [ "${USE_DOCKER:-false}" = "true" ]; then
  "${COMPOSE[@]}" exec -T backend python -m app.tools.rls_drill
else
  (cd "$ROOT_DIR" && PYTHONPATH=backend "$ROOT_DIR/.venv/bin/python" -m app.tools.rls_drill)
fi

echo ""
echo "=== Demo complete ==="
