#!/usr/bin/env bash
set -eu

mkdir -p "${OUTPUTS_DIR:-/data/outputs}"

python3 -m uvicorn backend.main:app --host 0.0.0.0 --port "${BACKEND_PORT:-8000}" &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

cd /app/frontend-runtime
node server.js &
FRONTEND_PID=$!

wait -n "$BACKEND_PID" "$FRONTEND_PID"
