#!/usr/bin/env bash
# One-command dev start.
#   ./dev.sh          backend + dashboard on http://0.0.0.0:8000 (N = CLEAR_AFTER_MIN, default 3)
#   ./dev.sh demo     same, plus the simulator, with N = 0.5 min so red tables show up quickly
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements-dev.txt
fi

PORT="${PORT:-8000}"
if [ "${1:-}" = "demo" ]; then
  export CLEAR_AFTER_MIN="${CLEAR_AFTER_MIN:-0.5}"
  export TABLEWATCH_DB="${TABLEWATCH_DB:-demo.db}"
  ( sleep 2 && exec .venv/bin/python simulator.py --url "http://localhost:$PORT" ) &
  SIM_PID=$!
  trap 'kill $SIM_PID 2>/dev/null || true' EXIT
fi

echo "Dashboard: http://localhost:$PORT  (from an iPad: http://<this-computer-ip>:$PORT)"
.venv/bin/uvicorn backend.app:create_app --factory --host 0.0.0.0 --port "$PORT"
