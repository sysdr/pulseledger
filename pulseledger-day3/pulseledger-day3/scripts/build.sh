#!/usr/bin/env bash
# PulseLedger Day 3 — build.sh
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$ROOT_DIR"

if [ "${USE_DOCKER:-false}" = "true" ]; then
  echo "==> Building with Docker (postgres, redis, backend, frontend)"
  "${COMPOSE[@]}" pull postgres redis
  "${COMPOSE[@]}" build
  echo "Build complete: 4 services ready (docker)"
  exit 0
fi

PYTHON_BIN="${PYTHON_BIN:-python3.13}"
if ! command -v "$PYTHON_BIN" >/dev/null; then
  echo "Python 3.13 not found. Install it (e.g. 'uv python install 3.13') or set PYTHON_BIN." >&2
  exit 1
fi

echo "==> Building backend ($("$PYTHON_BIN" --version))"
"$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$ROOT_DIR/.venv/bin/pip" install --quiet -r backend/requirements.txt

echo "==> Building frontend"
cd "$ROOT_DIR/frontend"
npm ci --no-audit --no-fund
NEXT_PUBLIC_API_BASE="http://localhost:$BACKEND_PORT" npx next build

[ -f "$ROOT_DIR/.env" ] || cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
echo "Build complete: backend + frontend ready"
