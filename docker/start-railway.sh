#!/bin/sh
set -eu

mkdir -p \
  "${OUTPUTS_DIR:-/data/outputs}" \
  "${RUNS_DIR:-/data/runs}" \
  "${REPORTS_GENERATED_DIR:-/data/reports/generated}" \
  "${REPORTS_AUDITS_DIR:-/data/reports/audits}" \
  "${REPORTS_EVALS_DIR:-/data/reports/evals}"

echo "Starting Smart Report on Railway"
echo "  public port: ${PORT:-3000}"
echo "  backend port: ${BACKEND_PORT:-8000}"
echo "  runs dir: ${RUNS_DIR:-/data/runs}"
echo "  generated reports dir: ${REPORTS_GENERATED_DIR:-/data/reports/generated}"

python3 -m uvicorn backend.main:app --host 0.0.0.0 --port "${BACKEND_PORT:-8000}" &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

cd /app/frontend-runtime
node server.js &
FRONTEND_PID=$!

while :; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    wait "$BACKEND_PID"
    exit 1
  fi

  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    wait "$FRONTEND_PID"
    exit 1
  fi

  sleep 2
done
