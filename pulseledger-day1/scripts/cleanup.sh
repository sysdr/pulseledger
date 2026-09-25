#!/usr/bin/env bash
# PulseLedger Day 1 — cleanup.sh
# Stops local/Docker services, removes build artifacts not needed for git push,
# and prunes unused Docker resources.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Stopping local processes"

for name in backend frontend; do
  pidfile="$ROOT_DIR/.run/$name.pid"
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      # Also stop child process groups started by the shell (uvicorn / next)
      pkill -P "$pid" 2>/dev/null || true
      echo "Stopped $name (pid $pid)"
    else
      echo "Stale pidfile for $name (pid $pid)"
    fi
    rm -f "$pidfile"
  fi
done

# Belt-and-suspenders: free Day 1 ports if something is still bound
for port in 8001 4001; do
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  elif command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "${pids:-}" ]; then
      # shellcheck disable=SC2086
      kill $pids 2>/dev/null || true
    fi
  fi
done

echo "==> Removing local artifacts (not useful for git push)"

rm -rf \
  "$ROOT_DIR/.venv" \
  "$ROOT_DIR/.run" \
  "$ROOT_DIR/frontend/node_modules" \
  "$ROOT_DIR/frontend/.next" \
  "$ROOT_DIR/frontend/out" \
  "$ROOT_DIR/frontend/.turbo"

find "$ROOT_DIR" \
  \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) \
  -type d -prune -exec rm -rf {} + 2>/dev/null || true

find "$ROOT_DIR" \
  \( -name '*.py[cod]' -o -name '*.log' -o -name '.DS_Store' -o -name 'Thumbs.db' \) \
  -type f -delete 2>/dev/null || true

# Strip accidental env/secret files if present (keep .env.example)
find "$ROOT_DIR" -maxdepth 3 -type f \( \
  -name '.env' -o -name '.env.local' -o -name '.env.*.local' -o \
  -name 'credentials.json' -o -name '*.pem' \
\) ! -name '.env.example' -print -delete 2>/dev/null || true

echo "==> Docker cleanup"

# WSL may ship a docker stub that exists but is not integrated with Docker Desktop.
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker not available — skipped container/image prune"
  echo "Cleanup complete"
  exit 0
fi

if [ -f "$ROOT_DIR/docker-compose.yml" ]; then
  docker compose -f "$ROOT_DIR/docker-compose.yml" down --remove-orphans \
    || docker-compose -f "$ROOT_DIR/docker-compose.yml" down --remove-orphans \
    || true
  echo "Stopped compose services"
fi

# Remove stopped containers, unused networks, unused images, and build cache
docker container prune -f
docker network prune -f
docker image prune -af
docker builder prune -af
docker volume prune -f

echo "Pruned unused Docker containers, images, networks, volumes, and build cache"
echo "Cleanup complete"
