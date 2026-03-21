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

## Railway

For Railway deployment, use the guide in [RAILWAY.md](RAILWAY.md).
