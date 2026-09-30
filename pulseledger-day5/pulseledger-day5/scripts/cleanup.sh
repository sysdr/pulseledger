#!/usr/bin/env bash
# PulseLedger Day 5 — cleanup.sh
#
# Stops native app processes, tears down Compose services, removes local
# artifacts that must not be git-pushed, and prunes unused Docker resources.
#
# Env:
#   PURGE=true   also delete Compose volumes (Postgres data) and prune volumes
#   KEEP_DEPS=true  keep .venv and frontend/node_modules
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$ROOT_DIR"

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

# Fall back: anything still bound to our ports
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  elif command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      # shellcheck disable=SC2086
      kill $pids 2>/dev/null || true
      echo "  freed port $port"
    fi
  fi
done

# Local redis started against this project's .run dir (native mode)
if [ -f "$ROOT_DIR/.run/redis.rdb" ] || [ -f "$ROOT_DIR/.run/redis.pid" ]; then
  if command -v redis-cli >/dev/null 2>&1; then
    redis-cli -h 127.0.0.1 -p 6379 shutdown nosave 2>/dev/null || true
    echo "  stopped local Redis on :6379"
  fi
fi

echo "==> Ensuring no secrets in .env"
if [ -f "$ROOT_DIR/.env" ]; then
  # Clear Stripe (and any accidental filled secret) while keeping structure
  if grep -q '^STRIPE_SECRET_KEY=' "$ROOT_DIR/.env"; then
    sed -i 's/^STRIPE_SECRET_KEY=.*/STRIPE_SECRET_KEY=/' "$ROOT_DIR/.env"
  fi
  echo "  STRIPE_SECRET_KEY cleared (empty)"
fi

echo "==> Stopping Docker Compose services"
if [ -n "${DOCKER_BIN:-}" ] && "${COMPOSE[@]}" version >/dev/null 2>&1; then
  if [ "${PURGE:-false}" = "true" ]; then
    "${COMPOSE[@]}" down --volumes --remove-orphans || true
    echo "  compose down --volumes (Postgres volume removed)"
  else
    "${COMPOSE[@]}" down --remove-orphans || true
    echo "  compose down (Postgres volume kept; PURGE=true to drop it)"
  fi

  echo "==> Pruning unused Docker resources"
  "$DOCKER_BIN" container prune -f >/dev/null
  "$DOCKER_BIN" image prune -f >/dev/null
  "$DOCKER_BIN" network prune -f >/dev/null
  if [ "${PURGE:-false}" = "true" ]; then
    "$DOCKER_BIN" volume prune -f >/dev/null
    # Drop project images that are no longer referenced
    "$DOCKER_BIN" image prune -a -f --filter "label=com.docker.compose.project=pulseledger-day5" >/dev/null 2>&1 || true
    echo "  pruned unused containers, images, networks, volumes"
  else
    echo "  pruned unused containers, dangling images, networks"
  fi
else
  echo "  Docker not available — skipped compose/prune"
fi

echo "==> Removing local artifacts (not for git push)"
rm -rf "$ROOT_DIR/.run" "$ROOT_DIR/.pytest_cache" "$ROOT_DIR/frontend/.next"
find "$ROOT_DIR" \
  \( -path "$ROOT_DIR/.venv" -o -path "$ROOT_DIR/frontend/node_modules" \) -prune -o \
  \( -type d -name '__pycache__' -o -name '*.pyc' -o -name '.DS_Store' -o -name '*.log' \) \
  -exec rm -rf {} + 2>/dev/null || true

if [ "${KEEP_DEPS:-false}" != "true" ]; then
  rm -rf "$ROOT_DIR/.venv" "$ROOT_DIR/frontend/node_modules"
  echo "  removed .venv, node_modules, caches, .run, .next"
else
  echo "  removed caches, .run, .next (KEEP_DEPS=true: left .venv + node_modules)"
fi

# .env stays local and gitignored; never push it
if [ -f "$ROOT_DIR/.env" ]; then
  echo "  .env present locally (gitignored) — not deleted"
fi

echo "Cleanup complete"
