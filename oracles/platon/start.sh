#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "▸ Platon UMBRAL — starting backend :9200 + frontend :5174"
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -e ".[dev]" -q
fi
export PLATON_PUBLIC_URL="${PLATON_PUBLIC_URL:-http://localhost:9200}"
.venv/bin/python -m uvicorn platon.main:app --host 0.0.0.0 --port 9200 &
BACK_PID=$!

cd "$ROOT/frontend"
npm install -q
npm run dev -- --host 0.0.0.0 --port 5174 &
FRONT_PID=$!

trap 'kill $BACK_PID $FRONT_PID 2>/dev/null' EXIT
echo "▸ Open http://localhost:5174"
wait
