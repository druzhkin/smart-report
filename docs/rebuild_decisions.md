# Smart Report V2 Rebuild Decisions

## Summary

The legacy backend is not being used as the v2 runtime core.
It remains in the repository as reference material because the worktree is already dirty and a mechanical delete would add unnecessary risk tonight.

The v2 slice is being implemented as a new evidence-first runtime under `backend/v2` and exposed through the main FastAPI entrypoints.

## Salvaged

- Existing repo structure, secrets, `.env`, deployment files, and Git history.
- Frontend shell and routing structure under `frontend/src/app/app`.
- Existing `ReportOutput`-style report envelope so the UI does not need a full redesign to render the first working slice.
- Useful rendering dependencies already present in the backend environment.

## Archived / Reference Only

- `backend/pipeline/graph.py`
- `backend/agents/research_agent.py`
- `backend/agents/synthesis_agent.py`
- `backend/agents/renderer.py`
- `backend/knowledge_library/*`
- Legacy prompt-routing / prompt-king / critique loop stack

These modules are not the foundation of v2. They remain as donor/reference code only.

## Rewritten From Scratch

- Request intake and semantic clarification contracts
- Task scoping and research planning
- Search provider abstraction
- Source selection / fetch / extraction flow
- Evidence ledger and claim table generation
- Recommendation authority gate
- Report package rendering and audit
- File-backed persisted run state and event log
- Report API flow around `create -> clarify -> scope -> run -> audit -> release`

## Why file-backed storage tonight

The TZ recommends Postgres, but it does not require enterprise completeness tonight.
For the overnight vertical slice, a file-backed artifact store is the safer choice because it:

- preserves every intermediate artifact as a real file;
- keeps the audit trail inspectable without DB tooling;
- avoids migration work while the contracts are still settling;
- still allows a later repository swap behind interfaces.

The data model remains explicit and split into separate artifacts rather than one opaque JSON blob.

## Patterns intentionally borrowed from `tripod`

- Strict typed contracts
- Bounded orchestration and stop policy
- Deterministic evidence artifacts before prose
- Recommendation authority gate
- Golden-eval methodology
- User-facing output checks

## Patterns intentionally rejected

- Full legacy LangGraph orchestration as the product backbone
- Prompt theater / long critique loops
- Renderer as hidden synthesis engine
- RAGFlow as a critical dependency
- Deep research as default path
