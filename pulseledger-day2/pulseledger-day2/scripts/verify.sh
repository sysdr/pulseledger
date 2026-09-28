#!/usr/bin/env bash
# PulseLedger Day 2 — verify.sh
# Liveness first, then readiness, each in a retry loop.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

BASE="http://127.0.0.1:$BACKEND_PORT"
MAX_ATTEMPTS=20

wait_for() {
  local label="$1" url="$2"
  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    if body=$(curl -sf "$url"); then
      echo "$body"
      echo "verify: $label OK (attempt $attempt)"
      return 0
    fi
    echo "verify: $label not ready yet (attempt $attempt/$MAX_ATTEMPTS)"
    sleep 1
  done
  echo "verify: $label FAILED" >&2
  curl -s "$url" >&2 || true
  echo "" >&2
  return 1
}

wait_for "liveness " "$BASE/api/health"
wait_for "readiness" "$BASE/api/ready" | tail -1
curl -s "$BASE/api/ready" | python3 "$ROOT_DIR/scripts/_report.py" summary
