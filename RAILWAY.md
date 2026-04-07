# Railway Deployment

This repository is now prepared for the **simplest honest Railway topology**:

- one Railway app service from the repo root
- one Railway Postgres service
- one Railway Redis service
- one Railway volume mounted at `/data`

That is **demo-ready and small-production-ready** for a single Smart Report instance.
It is **not** the right shape if you need independent frontend/backend scaling, zero-downtime deploys, or isolated background workers. In that case, split the app into separate Railway services later.

## What actually runs

The root [Dockerfile](C:\Users\rodina-adm\Documents\dev\smart-report\Dockerfile) builds:

- the Next.js frontend as a standalone server
- the FastAPI backend

The container starts both processes via [docker/start-railway.sh](C:\Users\rodina-adm\Documents\dev\smart-report\docker\start-railway.sh):

- frontend on Railway public port `${PORT}`
- backend on internal port `${BACKEND_PORT}`, default `8000`

Frontend requests hit the backend through `http://127.0.0.1:${BACKEND_PORT}` inside the same container.

## Railway config-as-code

The repo now includes [railway.toml](C:\Users\rodina-adm\Documents\dev\smart-report\railway.toml) with:

- Dockerfile builder
- healthcheck path `/api/healthz`
- restart policy `on_failure`
- watch patterns for backend, frontend, Docker, and Railway config changes

## Required Railway services

Create inside one Railway project:

1. App service from this repository root
2. Postgres service
3. Redis service

Then enable **Public Networking** for the app service so it gets a `*.railway.app` domain.

## Required variables

Set these on the **app service**:

```env
POSTGRES_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}

OPENROUTER_API_KEY=...
PERPLEXITY_API_KEY=...

BACKEND_PORT=8000
BACKEND_URL=http://127.0.0.1:8000
ENABLE_APO_SCHEDULER=false

OUTPUTS_DIR=/data/outputs
RUNS_DIR=/data/runs
REPORTS_GENERATED_DIR=/data/reports/generated
REPORTS_AUDITS_DIR=/data/reports/audits
REPORTS_EVALS_DIR=/data/reports/evals

CORS_ALLOWED_ORIGINS=https://<your-app>.up.railway.app
```

### Optional variables

```env
LANGSMITH_API_KEY=...
LANGCHAIN_TRACING_V2=false
LANGCHAIN_PROJECT=smart-report

DEEPGRAM_API_KEY=...
GAMMA_API_KEY=...
FIRECRAWL_API_KEY=...

RAGFLOW_API_KEY=
RAGFLOW_BASE_URL=
RAGFLOW_REPORTS_DATASET_ID=
RAGFLOW_FACTS_DATASET_ID=

NEXT_PUBLIC_VAPID_KEY=
VAPID_PRIVATE_KEY=
```

## Volume

Attach a Railway volume to the **app service** and mount it at `/data`.

That is now meaningful because runtime artifacts are configurable and should point to `/data`:

- report packages
- run events
- audit snapshots
- generated outputs

Without the volume, deploys will still run, but generated reports will be ephemeral.

## Deploy steps

1. Push the repo.
2. In Railway, create a new project and connect the repo.
3. Keep the service root at the repo root.
4. Confirm Railway uses the root [Dockerfile](C:\Users\rodina-adm\Documents\dev\smart-report\Dockerfile).
5. Add Postgres and Redis.
6. Add the variables above.
7. Mount the volume at `/data`.
8. Generate a public domain.
9. Deploy.

## Health and smoke checks

After deploy, these should respond:

- `https://<your-app>.up.railway.app/api/healthz`
- `https://<your-app>.up.railway.app/api/health`
- `https://<your-app>.up.railway.app/app/new`

## Known limits of this topology

- Frontend and backend share one container, so one crash takes down both.
- Horizontal scaling is awkward because filesystem-backed runs/reports are local to the mounted volume.
- Long-running report jobs still execute in the web container.

If this becomes a real production workload, the next step is not more Docker tweaking. The next step is to split:

- web
- api
- worker
- persistent object storage for report packages
