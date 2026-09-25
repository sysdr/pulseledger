#!/usr/bin/env bash
# PulseLedger Day 1 — test.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Running backend test suite"
"$ROOT_DIR/.venv/bin/python" -m pytest tests/ -v -c backend/pytest.ini
