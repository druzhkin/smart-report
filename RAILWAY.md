# Railway Deployment

This repo is ready to run on Railway as two app services plus managed data services:

- `backend` - FastAPI / LangGraph API
- `frontend` - Next.js app
- Railway Postgres
- Railway Redis

RAGFlow is optional and is not recommended for the first Railway deploy. Leave it disabled unless you plan to host it separately.

## Services

Create two services from the same GitHub repo.

### Backend service

Use:

- Dockerfile path: `Dockerfile.railway.backend`
- Public domain: enabled
- Healthcheck path: `/api/healthz`

Recommended variables:

```env
OPENROUTER_API_KEY=...
PERPLEXITY_API_KEY=...
DEEPGRAM_API_KEY=...
POSTGRES_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
OUTPUTS_DIR=/data/outputs
ENABLE_APO_SCHEDULER=false
RAGFLOW_API_KEY=
RAGFLOW_BASE_URL=
RAGFLOW_REPORTS_DATASET_ID=
RAGFLOW_FACTS_DATASET_ID=
```

Attach a Railway volume and mount it at `/data` if you want generated files (`pdf`, `docx`, `pptx`, charts) to survive redeploys.

### Frontend service

Use:

- Dockerfile path: `Dockerfile.railway.frontend`
- Public domain: enabled

Recommended variables:

```env
BACKEND_URL=http://${{backend.RAILWAY_PRIVATE_DOMAIN}}
```

If you prefer calling the public backend domain instead of the private network, set `BACKEND_URL` to your backend HTTPS URL.

## Notes

- Backend now accepts both `POSTGRES_URL` and Railway-style `DATABASE_URL`.
- Backend Docker healthcheck uses `/api/healthz`, which is intentionally lightweight and does not depend on OpenRouter, Perplexity, or RAGFlow.
- The main API health endpoint `/api/health` still reports upstream dependency status for diagnostics.
- The frontend build blocker caused by `LayoutPresentation` has been fixed, so the Next.js service can build on Railway.

## First deploy checklist

1. Create `backend` service from this repo and point it to `Dockerfile.railway.backend`.
2. Add Railway Postgres and Railway Redis.
3. Wire backend env vars.
4. Add a volume to backend at `/data`.
5. Create `frontend` service from this repo and point it to `Dockerfile.railway.frontend`.
6. Set `BACKEND_URL` on frontend to `http://${{backend.RAILWAY_PRIVATE_DOMAIN}}`.
7. Generate a public domain for frontend.

## Optional production tightening

- Set `DEV_MODE=false`
- Keep `ENABLE_APO_SCHEDULER=false`
- Add `NEXT_PUBLIC_VAPID_KEY` and `VAPID_PRIVATE_KEY` only if you want web push
- Add `GAMMA_API_KEY` only if you want PPTX generation through Gamma
