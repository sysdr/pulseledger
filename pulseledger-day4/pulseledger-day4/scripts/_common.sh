#!/usr/bin/env bash
# Shared helpers for PulseLedger Day 4 scripts.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8004
FRONTEND_PORT=4004
COMPOSE=(docker compose -f "$ROOT_DIR/docker-compose.yml")

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
