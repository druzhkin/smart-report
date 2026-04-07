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
FRONTEND_PID=""

cleanup() {
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  kill "$BACKEND_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

BACKEND_HEALTH_URL="http://127.0.0.1:${BACKEND_PORT:-8000}/api/healthz"
BACKEND_HEALTHCHECK_RETRIES="${BACKEND_HEALTHCHECK_RETRIES:-60}"
BACKEND_HEALTHCHECK_SLEEP_SEC="${BACKEND_HEALTHCHECK_SLEEP_SEC:-1}"

attempt=1
while [ "$attempt" -le "$BACKEND_HEALTHCHECK_RETRIES" ]; do
  if curl -fsS "$BACKEND_HEALTH_URL" >/dev/null 2>&1; then
    echo "Backend readiness check passed on attempt ${attempt}/${BACKEND_HEALTHCHECK_RETRIES}"
    break
  fi

  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Backend exited before readiness check passed"
    wait "$BACKEND_PID"
    exit 1
  fi

  echo "Waiting for backend readiness on ${BACKEND_HEALTH_URL} (${attempt}/${BACKEND_HEALTHCHECK_RETRIES})"
  attempt=$((attempt + 1))
  sleep "$BACKEND_HEALTHCHECK_SLEEP_SEC"
done

if [ "$attempt" -gt "$BACKEND_HEALTHCHECK_RETRIES" ]; then
  echo "Backend readiness check timed out after ${BACKEND_HEALTHCHECK_RETRIES} attempts"
  exit 1
fi

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
