# Repository Guidelines

## Project Structure & Module Organization

This repository contains a Python analytical engine and a Next.js frontend.

- `smart_report/`: backend package. API routes are in `smart_report/api/`, source adapters in `smart_report/sources/`, and exporters in `smart_report/exporters/`.
- `frontend/`: Next.js 14 app. Routes live in `frontend/app/`, components in `frontend/components/`, and API helpers in `frontend/lib/`.
- `tests/`: pytest suite. Files follow `test_*.py`; adapter tests live in `tests/sources/`.
- `prompts/`: editable role prompts used by the reporting pipeline.
- `scripts/`, `eval/`, `docs/`, `reference/`: diagnostics, baselines, and project notes.

## Build, Test, and Development Commands

- `pip install -e .[dev]`: install the backend package with pytest and ruff.
- `python run.py --dry-run "question"`: run the CLI without live external calls.
- `pytest`: run the default test suite, excluding `expensive` and `live` tests by config.
- `pytest -m live` or `pytest -m expensive`: run provider or costly model tests.
- `ruff check .`: lint Python code using the repo’s configured rules.
- `cd frontend && npm run dev`: start the local Next.js dev server.
- `cd frontend && npm run build`: build for production.
- `cd frontend && npm run lint`: run Next linting.

## Coding Style & Naming Conventions

Backend code targets Python 3.11. Use 4-space indentation, type hints where helpful, and Pydantic models for structured data. Ruff checks `E`, `F`, `W`, `I`, `B`, and `UP`; line length is 100.

Frontend code uses TypeScript, React, Tailwind, and Next app-router conventions. Name components in `PascalCase`, hooks as `useSomething`, and route files as `page.tsx`, `layout.tsx`, or `route.ts`.

## Testing Guidelines

Add focused pytest coverage for backend behavior and API contracts. Keep fast deterministic tests unmarked. Mark provider calls with `@pytest.mark.live` and costly model/evaluation tests with `@pytest.mark.expensive`. Prefer fixtures under `tests/fixtures/`.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit style, for example `feat(api): ...`, `fix(report-ui): ...`, and `fix(llm): ...`. Keep subjects scoped and imperative.

PRs should include a behavior summary, tests run, linked issues, and screenshots for visible frontend changes. Call out new environment variables or provider dependencies.

## Security & Configuration Tips

Keep API keys in local `.env` files; never commit secrets or generated run artifacts.

## Agent-Specific Instructions

Do not agree reflexively with proposed changes. Point out weak assumptions, risky shortcuts, and inconsistent plans directly, then propose the clearest workable alternative.
