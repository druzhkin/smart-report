# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Sibling repos — know which one you're in

- `smart-report-mvp/` (this dir) — **production/v2**. Heavy: 15+ agents, corpus-first flow, depth profiles, docx/pptx exporters, intake dialog. The thing users actually run.
- `../smart-report-mvp-v3/` — **clean rewrite**. `smart_report/` Python package, `tests/` with pytest, `runs/` for artefacts. 5 agents, Protocol-based `EventEmitter`. Use it as a reference for "what clean looks like" but **do not** port v2 changes into it without being asked.

If the user says "v3" or cites `smart_report/...`, they mean the sibling repo, not this one.

### Remote mapping (2026-04-18)

Both repos share one GitHub remote `druzhkin/smart-report`:
- `main` branch — this v2 repo. Connected to Railway production (Node.js build for `frontend/`).
- `v3` branch — the `smart-report-mvp-v3/` sibling. **Not** auto-deployed; deploying v3 requires a new Railway service (Python FastAPI) and is a deliberate future task.

v2 prod on Railway is effectively unused — primary usage is local dev.

## Common commands

```bash
# Activate venv (Git Bash on Windows)
source .venv/Scripts/activate

# CLI — single pass
python cli.py "<goal>"                            # fresh run → output/<ts>-<slug>.{md,json,docx}
python cli.py --from-json <path> --deepen "<Domain / Layer>" --focus "..."
python cli.py --from-json <path> --add-domain "<Name>" --layers "L1, L2, L3"
python cli.py --from-json <path> --connect "<Domain A>" "<Domain B>"

# FastAPI backend
uvicorn api.main:app --reload --port 8000         # docs at /docs

# Frontend (Next.js 14 App Router)
cd frontend && npm run dev                         # :3000, rewrites /api → :8000

# Pre-push guard against git-add near-miss (runs importlib on all pipeline modules)
python scripts/check_imports.py

# Single-shot probes / benches live at the repo root as `_probe_*.py`, `bench_*.py`
python _probe_pplx_cheap.py                       # example
```

No pytest suite lives here — tests are in the v3 sibling. Don't spend time looking for `tests/`.

## The UTF-8 curl trap (Windows bash)

Cyrillic or em-dash in a bash-expanded curl `-d` body gets mangled before the request leaves the shell, producing false 400s. Use `curl --data-binary @body.json` or write the request in Python. Background: `memory/windows_bash_utf8_curl_trap.md`.

## Architecture — the big picture

Pipeline is `goal → Matrix → Blocks → Connections → Report`, all async, passed as Pydantic models defined in `models.py`.

1. **Planner** (`agents/planner.py`) — goal → `Matrix` (domains × layers, each cell has a concrete `ScoutTask`).
2. **Corpus or Scouts** — two mutually exclusive retrieval modes gated by `USE_CORPUS_FLOW`:
   - **Corpus-first** (`corpus_fetch.py` → `corpus_mapper.py`): one deep-research fetch across Valyu / sonar-deep-research / gpt-researcher, then LLM maps each source to cells; gap-filling scouts only run for under-covered cells. This is the preferred path for new depth tiers.
   - **Legacy fanout** (`agents/scout.py` × N): per-cell Perplexity queries in bounded-parallel `asyncio.Semaphore(MAX_PARALLEL_SCOUTS)`.
3. **Analyst** (`agents/analyst.py`) per cell → `Block` (conclusion + findings + ACH-style assumptions/gaps).
4. **Contrarian** (`agents/contrarian.py`) — optional per-depth critic pass that attaches weaknesses/strongest_point to each block. Gated by `USE_CONTRARIAN_PASS` and depth profile.
5. **Bisociator** (`agents/bisociator.py`) — blocks → cross-domain `Connection`s.
6. **Summarizer** (`agents/summarizer.py`) → `ExecutiveSummary` that feeds both DOCX and the frontend's hero card.

All five+ roles route LLM calls through `llm.py:call_text` which:
- Reads model by role from `config.model_for(role)`, honouring the active `ContextVar` depth profile.
- Falls back between OpenRouter and the AWstore proxy by key prefix.
- Accumulates spend into a process-local meter surfaced at `/api/research/{id}/cost`.

### Depth profiles are the primary knob

`config.DEPTH_PROFILES` (`light | standard | deep | premium`/`exhaustive`) controls every expensive decision: models per role, parallelism caps, corpus backend list, Valyu mode, contrarian on/off, cost cap. `TIER_ALIASES` maps the UI tiers (`quick_take` → `light` etc.). Profile is activated via `set_active_profile()` at the top of each orchestrator entry-point — **every** cost-relevant call site must resolve via `profile_*()` or `model_for()`, not the raw `settings` dataclass.

### Reports are files, not a DB

`reports/{id}.json` is the single source of truth for one run. Sidecars: `{id}.status.json` (phase/updated_at heartbeat — used by the API to detect stale jobs after a Railway redeploy kills the worker), `{id}.cost.json`, `{id}.docx|.pptx|.onepager.html|.gamma.{fmt}.json`. `_` prefix or `.status` suffix excludes a file from `/api/reports`.

### FastAPI ↔ Frontend event contract

`api/main.py` holds a `_Job` per run with `events: list[dict]` and an `asyncio.Queue`. The frontend `LivePipeline` / `useSSE` hook polls `GET /api/research/{id}/events?since=<cursor>` (SSE via `/stream` exists as a fallback but Railway's HTTP/2 proxy kills long-lived streams). Three regexes on the client are load-bearing — don't change message shapes without updating them:

- scout messages start with `[{cell_id}]`
- analyst-done messages contain `готов`
- bisociator summary matches `/Найдено связей:\s*(\d+)/`

### Exports

`export.py` → md/json; `export_docx.py` → McKinsey-grade DOCX (preferred when it exists, else `save_all` baseline); `export_pptx.py` → PPTX; `export_onepager*.py` → HTML + DOCX one-pagers; `export_gamma.py` → Gamma API (PPTX/PDF, cached at `reports/{id}.gamma.{fmt}.json`).

## Prompts are the primary iteration surface

Every agent loads its system prompt from `prompts/<role>.md` via `config.load_prompt`. Editing prompts **is** the way to change behaviour — model code is a thin wrapper. The Scout prompt is notoriously sensitive to permissive phrasing (see `memory/scout_prompt_permissive_outputs.md`); prefer effort-demanding wording over escape hatches like "return [] if nothing matches".

## Frontend notes

Next.js 14 App Router, React 18, Tailwind, Framer Motion, D3 for the `ConnectionsGraph`. `lib/api.ts` is the typed client; `lib/useSSE.ts` is a polling hook despite the name. `next.config.mjs` rewrites `/api/*` to `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`). Dark/light theming via `ThemeToggle.tsx` with system-preference default.

## Auto-memory

User-level persistent memory lives at `C:\Users\rodina-adm\.claude\projects\C--Users-rodina-adm-Documents-dev-smart-report-mvp\memory\`. Check `MEMORY.md` there for vendor-reliability notes, prior incidents (Railway access, planner determinism, untracked-files near-miss), and key handling (Valyu / Parallel / Firecrawl status). Treat it as load-bearing context for anything touching search backends or deployment.
