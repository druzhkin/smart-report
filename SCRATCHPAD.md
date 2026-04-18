# Scratchpad — night 01 (2026-04-18)

Каждый трек дописывает снизу одну строку каждые ~20 минут:
`[HH:MM] Track X: <status>, <finding>`

Критичные находки жирно.

---
[01:46] Orchestrator: repo initialized, references copied, 4 tracks spawning in parallel.
[01:52] Track D: started, references read, verbatim anti-patterns grepped (lines 115/126/469 of v2_output). Drafting planner_v1.
[01:58] Track B: scaffolding done (b1..b5 + _common), ground truth extracted (Донстрой 0%, MR 5.65%, Level 8.67%, Эталон 35.46%, Sminex N/A). Starting live runs.
[02:05] Track C: scripts/baseline_eval scaffolded (judge.py + run_baseline.py). Launching 15 sonnet-4.6 calls.
[02:25] Track C: **15/15 calls green, $1.08 (<$3 cap)**. eval/baseline.md written. **OpenAI DR wins Coverage (10/10) + Cross-domain (9); Perplexity wins Honesty (82) + lowest triviality (5); v2 wins nothing.** Judge calibrated (2/2 URL spot-checks via WebFetch PASS, v2 coverage=1 manually confirmed).
[01:53] Track A: skeleton complete, 9/9 tests green, --dry-run produces valid Report JSON (4 blocks + 2 cross-links). Files: 16, max 154 lines. No real LLM calls. $0 spent.
[02:08] Track B: bake-off done. 5 strategies × 5 devs, $0.10 total. **B2 (sonar-pro + domain filter) is best** — 1/5 hits, 1/4 accurate vs OpenAI DR 4/4. **Scout IS the main blocker for numeric tasks**: PPLX unstable (B2 rerun 1→0 accurate), B3 hallucinates 19%/30% instead of 0%/8.67%, erzrf.ru is Angular SPA — static fetch useless. v3 needs B2 + Firecrawl JS-render layer.
[02:55] Track D: done. v1 + v2 planner runs on Opus (~$0.48 total), v2 wins — 7 domains × 14 cells, concrete numeric queries (HHI/NPS/LTV/absorption), diversified sources (СП 42.13330, ППМ 1521, Мосжилинспекция) vs v1 vendor-heavy + duplicate buyer layers. JSON validates against Matrix schema. 4 final prompts + notes + history ready to commit.

---

# v4 BUILD — 2026-04-18 (second session, evening)

Branch: `v4` (this repo) + `v4` on sibling `smart-report-mvp/` for frontend.
Spec: `../smart-report-mvp/_v4_spec.md` (full 727 lines).
Timebox: 3-5 h. Budget: $8.

## Philosophy

v4 = meta-analysis layer on top of v3. No retrieval. Analyst pastes external reports; three Opus-4.7 agents reason over them.

v3 untouched except allow-list: `api/main.py` (mount v4 router), `events.py` (phases), `models.py` (append), `LivePipeline.tsx` (phase map).

## Tracks

- **A** — Prompt Master + v4 models + orchestrator skeleton + first endpoints (~75 min)
- **B** — Analyzer + Synthesizer + export adapter + rest of endpoints (~120 min, starts ~20 min after A)
- **C** — Frontend v4 (6 screens) in sibling `smart-report-mvp/frontend/` (~90 min, starts ~25 min after A)

## Dependencies

- A → B (shared pydantic models; B extends models.py)
- A → C (first endpoint `POST /sessions`)
- B → C (analyze/synthesize/upload endpoints, final schemas)

## Live status (agents update here every ~30 min)

[03:15] Track A: done — 23/23 new tests green (70 total, v3 untouched). prompt_master.py + prompts/prompt_master.md (3-domain few-shot + 6 anti-patterns) + v4_orchestrator.py skeleton + api/v4_endpoints.py (POST /sessions + /generate-prompt live; Track B stubs return 501) + v4 schemas appended to models.py. Model ID: anthropic/claude-opus-4-7. Cost-meter hook `_accumulate_cost` stubbed — llm.py already writes per-call cost to llm_log.jsonl, so Track B or follow-up wires the session-level aggregate.
[04:05] Track B: done — 85/85 tests green (v3 + all Track A + 15 new Track B). Analyzer + Synthesizer on Opus-4.7 with JSON-retry + tolerant coercion. Adapter v4_to_report.py flattens FinalReport into a uniform dict; fresh v3-native exporters in smart_report/exporters/render.py cover md/json/onepager/docx/pptx + gamma stubs (Gamma is JSON-stub until API key wired — v2 exporters are too heavy to reuse, shape is v2-Report-specific not v4). v4_orchestrator.analyze/synthesize filled; status transitions wired. api/v4_endpoints.py: upload-reports/upload-followup (multipart, tool-detection from content markers), analyze, synthesize, get, events (long-poll), export (7 formats). Full-cycle integration test covers upload→analyze→synthesize→export/md/json/gamma-pdf. Cost: $0 (all LLM mocked). Commit next. **Adapter strategy: fresh exporters in v3, NOT v2 reuse** — v2's Report model has goal/matrix.domains/block_headers that don't map onto v4's Q→analyze→synthesize flow; writing thin v3-native renderers was cleaner than adapting v4 to v2's shape.

## Hard rules

- Opus-4.7 ONLY for the 3 new LLM calls (Prompt Master, Analyzer, Synthesizer). Don't swap.
- No retrieval API calls from v4 code.
- Files < 400 lines each.
- Each of 3 prompt .md files MUST contain an anti-patterns section with concrete examples.
- All commits on `v4`, prefix `feat(v4):` / `fix(v4):` / `test(v4):`.
- All LLM calls logged to `runs/<ts>/llm_log.jsonl`.

## Stop & escalate signals (per §10)

- Prompt Master prompt is paraphrase of question
- v3 tests break
- Analyzer returns 0 gaps/conflicts on real data
- Export adapter incompatible
- Synthesizer weaker than inputs
[23:38] Track C: 6 screens + 4 components + apiV4.ts + apiV4Stubs.ts done. tsc clean, all routes 200, v3 untouched. STUB_MODE smoke OK. Files: 12 new, 1 extended (LivePipeline +mode prop). Committing on v4.
