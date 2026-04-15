FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg build-essential \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/package.json frontend/package-lock.json* frontend/
RUN cd frontend && npm install --no-audit --no-fund

COPY frontend/ frontend/
ENV NEXT_PUBLIC_API_BASE=http://localhost:8000
RUN cd frontend && npm run build

COPY . .

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
EXPOSE 8080

CMD bash -c "uvicorn api.main:app --host 0.0.0.0 --port 8000 & cd frontend && npm start -- --port ${PORT:-8080} --hostname 0.0.0.0"
