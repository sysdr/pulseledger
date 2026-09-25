#!/usr/bin/env bash
# PulseLedger Day 1 — run.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ "${USE_DOCKER:-false}" = "true" ]; then
  echo "==> Running with Docker"
  docker compose -f "$ROOT_DIR/docker-compose.yml" up -d
  echo "Backend listening on 8001"
  echo "Frontend ready on 4001"
  exit 0
fi

mkdir -p "$ROOT_DIR/.run"

echo "==> Starting backend on :8001"
"$ROOT_DIR/.venv/bin/uvicorn" app.main:app \
  --app-dir "$ROOT_DIR/backend" \
  --host 127.0.0.1 --port 8001 \
  > "$ROOT_DIR/.run/backend.log" 2>&1 &
echo $! > "$ROOT_DIR/.run/backend.pid"

echo "==> Starting frontend on :4001"
cd "$ROOT_DIR/frontend"
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001 npx next start -p 4001 \
  > "$ROOT_DIR/.run/frontend.log" 2>&1 &
echo $! > "$ROOT_DIR/.run/frontend.pid"

sleep 3
echo "Backend listening on 8001"
echo "Frontend ready on 4001"
