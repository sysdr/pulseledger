#!/usr/bin/env bash
# PulseLedger Day 4 — cleanup.sh
# Stops native app processes and Compose services, scrubs local secrets,
# removes gitignored build artifacts, and prunes unused Docker resources.
# PURGE=true also deletes Compose volumes (Postgres data) and dangling volumes.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$ROOT_DIR"

docker_bin() {
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    command -v docker
    return 0
  fi
  local win="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
  if [ -x "$win" ] && "$win" info >/dev/null 2>&1; then
    printf '%s\n' "$win"
    return 0
  fi
  return 1
}

echo "==> Stopping native app processes"
for name in backend frontend; do
  pidfile="$ROOT_DIR/.run/$name.pid"
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile")"
    kill "$pid" 2>/dev/null || true
    rm -f "$pidfile"
    echo "  stopped $name (pid $pid)"
  fi
done
# Catch orphans still bound to the day-4 ports
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${BACKEND_PORT}/tcp" 2>/dev/null || true
  fuser -k "${FRONTEND_PORT}/tcp" 2>/dev/null || true
fi
pkill -f "uvicorn app.main:app .*--port ${BACKEND_PORT}" 2>/dev/null || true
pkill -f "next start -p ${FRONTEND_PORT}" 2>/dev/null || true

echo "==> Scrubbing local secrets / API keys"
if [ -f "$ROOT_DIR/.env" ]; then
  # Clear any Stripe (or similar) secret values; keep structure for local re-use.
  sed -i -E \
    -e 's/^(STRIPE_SECRET_KEY)=.*/\1=/' \
    -e 's/^(.*_API_KEY)=.*/\1=/' \
    -e 's/^(.*_SECRET)=.*/\1=/' \
    -e 's/^(.*_TOKEN)=.*/\1=/' \
    "$ROOT_DIR/.env"
  echo "  scrubbed secret values in .env"
else
  echo "  no .env present"
fi

echo "==> Removing local artifacts (not for git push)"
rm -rf \
  "$ROOT_DIR/.run" \
  "$ROOT_DIR/.venv" \
  "$ROOT_DIR/.pytest_cache" \
  "$ROOT_DIR/.mypy_cache" \
  "$ROOT_DIR/.ruff_cache" \
  "$ROOT_DIR/.coverage" \
  "$ROOT_DIR/htmlcov" \
  "$ROOT_DIR/frontend/node_modules" \
  "$ROOT_DIR/frontend/.next" \
  "$ROOT_DIR/frontend/out" \
  "$ROOT_DIR/frontend/dist"
find "$ROOT_DIR" \
  \( -name '__pycache__' -o -name '.DS_Store' -o -name 'Thumbs.db' \) \
  -not -path '*/.git/*' \
  -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null || true
find "$ROOT_DIR" \
  \( -name '*.pyc' -o -name '*.pyo' -o -name '*.log' \) \
  -not -path '*/.git/*' \
  -delete 2>/dev/null || true
echo "  removed .run .venv caches node_modules .next __pycache__ logs"

DOCKER="$(docker_bin || true)"
if [ -z "${DOCKER:-}" ]; then
  echo "==> Docker not reachable; skipped Compose stop and prune"
  echo "Cleanup complete (local only)"
  exit 0
fi

COMPOSE=("$DOCKER" compose -f "$ROOT_DIR/docker-compose.yml")

echo "==> Stopping Compose services"
if [ "${PURGE:-false}" = "true" ]; then
  "${COMPOSE[@]}" down --volumes --remove-orphans
  echo "  stopped; Postgres volume removed"
else
  "${COMPOSE[@]}" down --remove-orphans
  echo "  stopped; Postgres data kept in volume pgdata"
fi

echo "==> Pruning unused Docker resources"
"$DOCKER" container prune -f >/dev/null
"$DOCKER" network prune -f >/dev/null
"$DOCKER" image prune -af >/dev/null
if [ "${PURGE:-false}" = "true" ]; then
  "$DOCKER" volume prune -f >/dev/null
  echo "  pruned unused containers, networks, images, and volumes"
else
  echo "  pruned unused containers, networks, and images"
fi

echo "Cleanup complete"
