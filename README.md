# Smart Report System

Multi-agent AI pipeline for generating McKinsey-grade analytical reports.

## Architecture

8-layer LangGraph pipeline:
1. **Intake** — parse user request, extract intent
2. **Prompt Router** — select optimal prompting techniques
3. **Prompt King** — compose master prompt
4. **Supervisor** — orchestrate research agents
5. **Research** — deep research via Perplexity + RAGFlow
6. **Reflect** — critique and improve research quality
7. **Render** — generate document, slides, visualizations
8. **QA** — final quality assurance

## Stack

- **Backend**: Python 3.12, FastAPI, LangGraph, OpenRouter
- **Frontend**: Next.js 15, shadcn/ui, Tailwind CSS
- **Database**: PostgreSQL, Redis
- **Knowledge**: RAGFlow (RAG pipeline)
- **Voice**: Deepgram STT
- **Tracing**: LangSmith

## Quick Start

```bash
cp .env.example .env
# fill in API keys

make install
make docker-up
make dev
```

## Development

```bash
make test      # run tests
make lint      # ruff check + fix
```

## Autonomous Audit

Run the full local audit (backend tests + frontend build + frontend e2e):

```bash
python scripts/full_audit.py
```

Optional flags:

```bash
FULL_AUDIT_RUN_INTEGRATION=1 python scripts/full_audit.py      # include backend e2e integration
SMOKE_API_BASE=https://<railway-domain>/api python scripts/full_audit.py  # include production smoke
```

## Autonomous Ops (Hands-Off)

One-time setup (sync GitHub Actions secrets from local `.env`):

```bash
# requires GitHub CLI: https://cli.github.com/
python scripts/bootstrap_github_secrets.py --repo <owner/repo> --smoke-api-base https://<railway-domain>/api
```

What autonomous mode does:

- Nightly `autonomous-audit` run (full audit + integration + production smoke).
- Generates machine-readable report: `outputs/audit/latest.json`.
- Generates human summary: `outputs/audit/summary.md`.
- Uploads both as workflow artifacts.
- Auto-creates GitHub Issue when audit fails.

Required CI secrets:

- `OPENROUTER_API_KEY`
- `SMOKE_API_BASE` (Railway backend public URL + `/api`)
- `SMOKE_RAGFLOW_BASE_URL` (external RAGFlow URL)
- `SMOKE_RAGFLOW_API_KEY`

Optional CI secrets:

- `SMOKE_RAGFLOW_REPORTS_DATASET_ID`
- `SMOKE_RAGFLOW_FACTS_DATASET_ID`
- `SMOKE_RUN_REPORT` (defaults to `1` in autonomous job)
- `SMOKE_REPORT_TIMEOUT_SEC`
- `SMOKE_REPORT_DEPTH` (`standard` by default)

## Railway

For Railway deployment, use the guide in [RAILWAY.md](RAILWAY.md).
