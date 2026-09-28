#!/usr/bin/env bash
# PulseLedger Day 2 — demo.sh
# 1) readiness snapshot  2) boot history from Postgres
# 3) Redis outage drill: ready -> degraded -> ready, live
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

BASE="http://127.0.0.1:$BACKEND_PORT"

state() {
  local code
  code=$(curl -s -o /tmp/pl-ready.json -w "%{http_code}" "$BASE/api/ready")
  python3 "$ROOT_DIR/scripts/_report.py" state "$code" < /tmp/pl-ready.json
}

echo "=== PulseLedger Day 2 Demo ==="
echo ""
echo "1. Readiness (every dependency answered a real query just now):"
curl -s "$BASE/api/ready" | python3 -m json.tool
echo ""
echo "2. Boot history, read back from the service_boots table:"
curl -s "$BASE/api/boots?limit=3" | python3 "$ROOT_DIR/scripts/_report.py" boots
echo ""

if [ "${USE_DOCKER:-false}" = "true" ]; then
  stop_redis()  { "${COMPOSE[@]}" stop redis >/dev/null; }
  start_redis() { "${COMPOSE[@]}" start redis >/dev/null; }
elif [ "${DEMO_OUTAGE:-false}" = "true" ] && command -v redis-server >/dev/null; then
  stop_redis()  { redis-cli -p 6379 shutdown nosave >/dev/null 2>&1 || true; }
  start_redis() { redis-server --port 6379 --save "" --daemonize yes >/dev/null; }
else
  echo "3. Outage drill skipped (runs automatically with USE_DOCKER=true,"
  echo "   or natively with DEMO_OUTAGE=true when redis-server is on PATH)."
  echo ""
  echo "Open http://localhost:$FRONTEND_PORT to see the same data rendered."
  echo "=== Demo complete ==="
  exit 0
fi

echo "3. Outage drill. Keep http://localhost:$FRONTEND_PORT open and watch it."
echo "   Before:"
state
echo "   Stopping Redis..."
stop_redis
sleep 4
echo "   During the outage:"
state
echo "   Liveness during the outage: $(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/health")"
echo "   Starting Redis again..."
start_redis
for _ in $(seq 1 15); do
  sleep 1
  curl -sf "$BASE/api/ready" >/dev/null && break
done
echo "   After:"
state
echo ""
echo "=== Demo complete ==="
