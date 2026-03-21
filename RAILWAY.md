# Railway Deployment

This repo is now prepared for the simplest Railway flow:

- one Railway app service from the repo root
- one Railway Postgres service
- one Railway Redis service

Railway will detect the root [Dockerfile](C:\Users\rodina-adm\Documents\dev\smart-report\Dockerfile) automatically, so you do not need to configure a start command in Railpack.

## What runs inside the container

The root Docker image starts:

- FastAPI backend on internal port `8000`
- Next.js frontend on public Railway port `${PORT}`

The frontend talks to the backend over `http://127.0.0.1:8000`, so no second Railway app service is required.

## Required Railway services

Create:

- app service from this GitHub repo
- Postgres
- Redis

## Required variables

Set these on the app service:

```env
POSTGRES_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
OPENROUTER_API_KEY=...
PERPLEXITY_API_KEY=...
OUTPUTS_DIR=/data/outputs
ENABLE_APO_SCHEDULER=false
BACKEND_PORT=8000
```

Optional:

```env
DEEPGRAM_API_KEY=...
GAMMA_API_KEY=...
NEXT_PUBLIC_VAPID_KEY=...
VAPID_PRIVATE_KEY=...
RAGFLOW_API_KEY=
RAGFLOW_BASE_URL=
RAGFLOW_REPORTS_DATASET_ID=
RAGFLOW_FACTS_DATASET_ID=
```

## Volume

Attach a Railway volume to the app service and mount it at `/data`.

That keeps generated reports and charts across redeploys.

## Why the previous deploy failed

Railway was trying to build the repo with Railpack as a plain Python app from the root, and the repo had no root start command. With the new root Dockerfile, Railway no longer needs to guess how to start the project.
