#!/usr/bin/env bash
# PulseLedger Day 1 — verify.sh
# Polls the backend health endpoint until it responds or times out.
set -euo pipefail

URL="http://127.0.0.1:8001/api/health"
MAX_ATTEMPTS=15

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  if response=$(curl -sf "$URL"); then
    echo "$response"
    echo "verify: OK (attempt $attempt)"
    exit 0
  fi
  echo "verify: backend not ready yet (attempt $attempt/$MAX_ATTEMPTS)"
  sleep 1
done

echo "verify: FAILED — backend never became healthy" >&2
exit 1
