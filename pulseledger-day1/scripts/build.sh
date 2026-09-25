#!/usr/bin/env bash
# PulseLedger Day 1 — build.sh
# Installs backend and frontend dependencies. Does NOT generate any source
# files — those already exist in backend/ and frontend/.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ "${USE_DOCKER:-false}" = "true" ]; then
  echo "==> Building with Docker"
  docker compose -f "$ROOT_DIR/docker-compose.yml" build
  echo "Build complete: backend + frontend ready (docker)"
  exit 0
fi

echo "==> Building backend"
python3 -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$ROOT_DIR/.venv/bin/pip" install --quiet -r backend/requirements.txt

echo "==> Building frontend"
cd "$ROOT_DIR/frontend"
npm install --no-audit --no-fund
npx next build

echo "Build complete: backend + frontend ready"
