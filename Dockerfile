FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ENV BACKEND_URL=http://127.0.0.1:8000
RUN npm run build

FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN python3 -m pip install --break-system-packages --no-cache-dir -r backend/requirements.txt

COPY . .

COPY --from=frontend-builder /app/frontend/.next/standalone ./frontend-runtime/
COPY --from=frontend-builder /app/frontend/.next/static ./frontend-runtime/.next/static
COPY --from=frontend-builder /app/frontend/public ./frontend-runtime/public

ENV PYTHONUNBUFFERED=1
ENV PORT=3000
ENV BACKEND_PORT=8000
ENV BACKEND_URL=http://127.0.0.1:8000
ENV OUTPUTS_DIR=/data/outputs
ENV ENABLE_APO_SCHEDULER=false

RUN chmod +x docker/start-railway.sh

EXPOSE 3000

CMD ["./docker/start-railway.sh"]
