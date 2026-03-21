.PHONY: install dev test lint docker-up docker-down migrate

install:
	pip install -e ".[dev]"
	cd frontend && npm install

dev:
	@echo "Starting backend..."
	uvicorn backend.main:app --reload --port 8000 &
	@echo "Starting frontend..."
	cd frontend && npm run dev

test:
	pytest -v
	cd frontend && npx playwright test

lint:
	ruff check backend/ --fix
	ruff format backend/

docker-up:
	docker compose up -d

docker-down:
	docker compose down

migrate:
	docker compose exec backend python -m backend.db.migrations
