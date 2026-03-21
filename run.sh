#!/bin/bash
set -e

case "$1" in
  docker-up)
    docker compose up -d
    ;;
  docker-down)
    docker compose down
    ;;
  docker-infra)
    docker compose up -d postgres redis ragflow_mysql ragflow_minio ragflow_redis ragflow
    ;;
  docker-restart-backend)
    docker compose up -d --force-recreate backend
    ;;
  docker-restart-frontend)
    docker compose up -d --force-recreate frontend
    ;;
  dev)
    echo "Starting backend..."
    cd backend && uvicorn backend.main:app --reload --port 8000 &
    echo "Starting frontend..."
    cd frontend && npm run dev
    ;;
  migrate)
    cd backend && alembic upgrade head
    ;;
  test)
    cd backend && python -m pytest tests/ -v --tb=short --ignore=tests/test_pipeline_e2e.py
    ;;
  lint)
    cd backend && ruff check . --fix && ruff format .
    ;;
  ragflow-health)
    curl -s http://localhost:9380/v1/health || echo "RAGFlow not ready"
    ;;
  *)
    echo "Usage: $0 {docker-up|docker-down|docker-infra|docker-restart-backend|docker-restart-frontend|dev|migrate|test|lint|ragflow-health}"
    exit 1
    ;;
esac
