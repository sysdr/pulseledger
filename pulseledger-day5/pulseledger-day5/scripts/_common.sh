#!/usr/bin/env bash
# Shared helpers for PulseLedger Day 5 scripts.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8005
FRONTEND_PORT=4005

# Resolve `docker` for native Linux or Docker Desktop via docker.exe (WSL).
# Prefer a working engine; the WSL `docker` stub can exist without a daemon.
resolve_docker() {
  local candidate
  for candidate in docker \
      "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" \
      docker.exe; do
    if ! command -v "$candidate" >/dev/null 2>&1 && [ ! -x "$candidate" ]; then
      continue
    fi
    if "$candidate" version >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

DOCKER_BIN="$(resolve_docker 2>/dev/null || true)"
if [ -n "${DOCKER_BIN:-}" ]; then
  COMPOSE=("$DOCKER_BIN" compose -f "$ROOT_DIR/docker-compose.yml")
else
  COMPOSE=(docker compose -f "$ROOT_DIR/docker-compose.yml")
fi

# port_open HOST PORT -> 0 if something accepts TCP connections there
port_open() {
  (exec 3<>"/dev/tcp/$1/$2") 2>/dev/null && exec 3>&- 3<&-
}

require_infra() {
  local missing=0
  port_open 127.0.0.1 5432 || { echo "  Postgres not reachable on 127.0.0.1:5432"; missing=1; }
  port_open 127.0.0.1 6379 || { echo "  Redis not reachable on 127.0.0.1:6379"; missing=1; }
  if [ "$missing" = 1 ]; then
    echo ""
    echo "Start them either natively, or with Docker for just the data services:"
    echo "  docker compose up -d postgres redis"
    exit 1
  fi
}
