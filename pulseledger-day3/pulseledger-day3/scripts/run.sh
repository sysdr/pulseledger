#!/usr/bin/env bash
# PulseLedger Day 3 — run.sh
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$ROOT_DIR"

if [ "${USE_DOCKER:-false}" = "true" ]; then
  echo "==> Starting the full stack with Docker Compose"
  "${COMPOSE[@]}" up -d --wait
  echo "Backend listening on $BACKEND_PORT"
  echo "Frontend ready on $FRONTEND_PORT"
  exit 0
fi

echo "==> Checking data services"
require_infra
echo "  Postgres and Redis reachable"

mkdir -p "$ROOT_DIR/.run"

echo "==> Starting backend on :$BACKEND_PORT"
"$ROOT_DIR/.venv/bin/uvicorn" app.main:app \
  --app-dir "$ROOT_DIR/backend" \
  --host 127.0.0.1 --port "$BACKEND_PORT" \
  > "$ROOT_DIR/.run/backend.log" 2>&1 &
echo $! > "$ROOT_DIR/.run/backend.pid"

echo "==> Starting frontend on :$FRONTEND_PORT"
cd "$ROOT_DIR/frontend"
"$ROOT_DIR/frontend/node_modules/.bin/next" start -p "$FRONTEND_PORT" > "$ROOT_DIR/.run/frontend.log" 2>&1 &
echo $! > "$ROOT_DIR/.run/frontend.pid"

sleep 3
echo "Backend listening on $BACKEND_PORT"
echo "Frontend ready on $FRONTEND_PORT"
