#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Checking .env"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "    Created .env from .env.example — fill in API keys before proceeding."
fi

echo "==> Installing frontend deps"
cd frontend && npm install && cd ..

echo "==> Installing backend deps"
pip install -e ".[dev]"

echo "==> Starting postgres + redis"
docker compose up -d postgres redis

echo "==> Waiting for postgres to be ready..."
until docker compose exec postgres pg_isready -U smartreport > /dev/null 2>&1; do
    sleep 1
done

echo "==> Applying migrations"
python -m backend.db.migrations

echo "==> Setup complete."
echo "    Run 'make dev' to start in development mode."
echo "    Run 'make docker-up' to start all services via Docker."

if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:3000
elif command -v open &>/dev/null; then
    open http://localhost:3000
fi
