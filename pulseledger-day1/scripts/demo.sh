#!/usr/bin/env bash
# PulseLedger Day 1 — demo.sh
# Shows exactly what today's lesson built: a backend that reports its own
# health, and a frontend that displays that status live.
set -euo pipefail

echo "=== PulseLedger Day 1 Demo ==="
echo ""
echo "1. Backend health check:"
curl -s http://127.0.0.1:8001/api/health
echo ""
echo ""
echo "2. Frontend homepage (open in a browser to see it rendered):"
echo "   http://localhost:4001"
echo ""
echo "3. What you should see on screen:"
echo "   - Title: 'PulseLedger'"
echo "   - Subtitle: 'Day 1: Foundations Laid'"
echo "   - A green dot with the text 'API: ok (day 1)', fetched live"
echo "     from the backend you just curled above"
echo ""
echo "=== Demo complete ==="
