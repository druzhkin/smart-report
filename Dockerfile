# Combined Next.js frontend + FastAPI backend deploy.
# Browser hits Next.js on $PORT (Railway-injected). Next.js's
# next.config.mjs rewrites /api/:path* → http://localhost:8000/api/:path*
# so the FastAPI backend (uvicorn on 8000 internal) receives /api/* traffic.
# Same-origin cookies just work. /landing/* + /app/* are served BY FastAPI
# in this layout — Next.js DOES NOT rewrite those paths, so Next.js will
# 404 them; we rewrite them through Next at the config level (see below).
#
# v4 chat UI lives in frontend/app/v4/chat/ (Workspace.tsx, fully wired
# to apiV4 lib that hits the rewritten /api/v4/sessions/* endpoints).

FROM python:3.12-slim

# System deps:
#   curl + ca-certificates for Node bootstrap
#   nodejs 20 for Next.js build + start
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1 — Python deps (rebuild only when requirements.txt changes)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2 — Node deps for the docx-js renderer (optional)
COPY smart_report/exporters/docx_js/package*.json smart_report/exporters/docx_js/
RUN if [ -f smart_report/exporters/docx_js/package.json ]; then \
        cd smart_report/exporters/docx_js && npm install --no-audit --no-fund --omit=dev ; \
    fi

# Layer 3 — Next.js frontend deps + build
COPY frontend/package.json frontend/package-lock.json* frontend/
RUN cd frontend && npm install --no-audit --no-fund

COPY frontend/ frontend/
# Build with empty NEXT_PUBLIC_API_BASE so client-side fetches use
# same-origin relative URLs (Next.js rewrites them to localhost:8000
# internally — see frontend/next.config.mjs).
ENV NEXT_PUBLIC_API_BASE=
ENV NEXT_PUBLIC_V4_API_BASE=
RUN cd frontend && npm run build

# Layer 4 — backend application code (changes most often)
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV PORT=8080
EXPOSE 8080

# Start both processes:
#   FastAPI on 8000 (internal, Next.js proxies /api/* here)
#   Next.js on $PORT (public, serves UI + proxies API + serves landing.html at /)
# `wait` keeps the container alive until either child dies, then exits
# so Railway restart policy kicks in.
CMD ["bash", "-c", "uvicorn smart_report.api.main:app --host 127.0.0.1 --port 8000 & cd frontend && npm start -- --port ${PORT:-8080} --hostname 0.0.0.0 & wait -n"]
