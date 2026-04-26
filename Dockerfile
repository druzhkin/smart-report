# Backend-only deploy for v4.5 architecture (smart_report/ package).
# Frontend lives in a separate worktree (smart-report-mvp/frontend, branch v4)
# and is deployed independently — this image serves the FastAPI backend only,
# including the /landing/ static React+Babel page (admin/admin Basic auth).

FROM python:3.12-slim

# System deps — minimal:
#   curl + ca-certificates: bootstrap Node for the docx-js renderer
#   nodejs: optional (smart_report/exporters/docx_js/) — falls back to
#           python-docx renderer if Node is absent (see render.py auto-select)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1 — pip deps (rebuild only when requirements.txt changes)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2 — Node deps for docx-js renderer (optional but ideal). Skips
# silently if package.json is absent (e.g. in old branches).
COPY smart_report/exporters/docx_js/package*.json smart_report/exporters/docx_js/
RUN if [ -f smart_report/exporters/docx_js/package.json ]; then \
        cd smart_report/exporters/docx_js && npm install --no-audit --no-fund --omit=dev ; \
    fi

# Layer 3 — application code (changes most often, last layer)
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
# Railway injects $PORT at runtime; default 8080 for local docker.
ENV PORT=8080
EXPOSE 8080

# /health endpoint exists in smart_report.api.main — Railway healthcheck
# in railway.toml hits /health (NOT /api/health from the old main branch).
CMD ["sh", "-c", "uvicorn smart_report.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
