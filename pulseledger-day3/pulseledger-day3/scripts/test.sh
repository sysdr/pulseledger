#!/usr/bin/env bash
# PulseLedger Day 3 — test.sh
# Tests hit the real Postgres and Redis. No mocks.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$ROOT_DIR"

if [ "${USE_DOCKER:-false}" = "true" ]; then
  echo "==> Running test suite inside the backend container"
  "${COMPOSE[@]}" run --rm --no-deps \
    -v "$ROOT_DIR/tests:/app/tests:ro" \
    -v "$ROOT_DIR/pytest.ini:/app/pytest.ini:ro" \
    backend python -m pytest -v
  exit 0
fi

require_infra
echo "==> Running test suite"
"$ROOT_DIR/.venv/bin/python" -m pytest -v
