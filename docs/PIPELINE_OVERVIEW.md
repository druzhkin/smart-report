# Pipeline Overview

How a research goal becomes a structured Report. Two flows coexist:

1. **Corpus-first flow (Variant E, default when `USE_CORPUS_FLOW=true`).** One holistic DR fetch across Valyu + Sonar DR + gpt-researcher (+ optional OpenAI/Gemini DR at `premium`), then a single LLM mapping pass attributes every claim to a matrix cell. Gap-fill scouts only run for low-coverage cells.
2. **Legacy scout-fanout.** One Scout agent per cell-plan task (~42 for `standard`). Used automatically as fallback when corpus flow is disabled or returns empty.

## Entry points

| Surface | File | Function |
| --- | --- | --- |
| CLI | `cli.py` | `_run_fresh` → `orchestrator.run_research` |
| HTTP (FastAPI) | `api/main.py` | `POST /api/research` |
| Chat intake | `agents/intake.py` | `intake_start` / `intake_answer` / `intake_confirm` |

All three converge on `orchestrator.run_research(goal, progress, matrix=None, depth, question_type_override=None)`.

## Depth tiers

Set via `--depth` or intake tier mapping (`TIER_ALIASES` in `config.py`):

| Depth | Alias | Matrix | Corpus backends | Valyu | Contrarian | Consensus | Cost cap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| light | quick_take | 2-3 × 1-2 | valyu + gpt_researcher | fast | off | off | $1.5 |
| standard | investment_brief | 3-4 × 2-3 | valyu + sonar_dr + gpt_researcher | fast | on | off | $3 |
| deep | strategy_note | 4-5 × 2-4 | valyu + sonar_dr + gpt_researcher | standard | on | off | $6 |
| premium | full_research (exhaustive alias) | 5-6 × 3-4 | + openai_dr + gemini_dr | fast | on | on | $25 |

`set_active_profile(depth_profile(depth))` at the top of `run_research` publishes the profile via `ContextVar`; agents read it through `model_for("role")` and `profile_bool/str/int/list`.

## Stages

### 1. Planner → Matrix

`agents/planner.py:planner(goal, depth)` → `models.Matrix`.

- `temperature=0.0` for determinism (see `planner_determinism_fixed.md`).
- Emits `Matrix.question_type` ∈ {factual, predictive, comparative, causal, normative, exploratory}.
- Matrix domain/layer counts constrained by profile (`depth_profile(depth)["domains"/"layers"]`).
- `--question-type` CLI flag overrides via `matrix.model_copy(update=…)` in orchestrator.

### 2. Corpus fetch (Variant E, when enabled)

`corpus_fetch.py:fetch_corpus(goal, strategy, backends, valyu_mode)` → `Corpus`.

Runs enabled backends in parallel (`asyncio.gather`), deduplicates sources by URL+DOI, keeps per-backend synth reports. Each `CorpusSource` carries `backend`, `year`, `is_peer_reviewed`, `citation_count`.

Strategy is built in `orchestrator._build_strategy(matrix)` from the matrix domains/layers — 2–5 sentences fed to every DR vendor so they don't drift too broad.

### 3. Corpus → cells mapping

`corpus_mapper.py:map_corpus_to_cells(corpus, matrix)` → `dict[cell, list[MappedFinding]]`.

- Single long-context Gemini 2.5 Flash call attributes claims to cells; batches per-domain if the corpus exceeds `_TOKEN_BUDGET_SINGLE_CALL` (~700k tokens).
- Post-LLM `_enrich_with_corpus_metadata` matches each finding's URL back to the `CorpusSource` pool and populates `source_backend`/`source_type`/`citation_count`/`publication_year`/`is_peer_reviewed` on the `MappedFinding`. `metadata_source` ∈ {`direct`, `synth`, `fallback`}.
- `orchestrator._mapped_to_scout_result` adapts `MappedFinding` → `ScoutResult`, propagating citation_count and year into `Finding`.
- `orchestrator._gap_fill_low_coverage` runs 3-level scout fallback (broader → international → pivot) only for cells below `CORPUS_MIN_FINDINGS_PER_CELL`.

### 4. Analyst per cell

`agents/analyst.py:analyst(cell, scout_results)` → `models.Block`.

Runs per-cell in bounded parallel (`profile_int("max_parallel_analysts")`). Emits summary, findings (passed through), gaps, analogies, assumptions, unverified_numerics.

### 5. Optional block-level passes

- **Quant extractor** (`agents/quant_extractor.py`): structured `QuantMetric` list per block before analyst narrative.
- **Contrarian** (`agents/contrarian.py`, `profile_bool("contrarian_enabled")`): appends `contrarian_critique` + `strongest_point` per block.
- **Doubt cycle** (`agents/_scaffold`, `profile_bool("doubt_cycle_enabled")`): scaffolded stub — not wired to refinement loop yet.

### 6. Bisociator → connections

`agents/bisociator.py:bisociator(blocks)` → `list[Connection]`. Finds cross-domain shared entities and novelty.

### 7. Consensus layer (Premium only)

`agents/consensus.py:build_consensus(goal, corpus.synth_reports)` → `ConsensusLayer` — cross-backend meta-analysis over DR synth reports. Populated only when `profile_bool("consensus_layer")`.

### 8. Summarizer → ExecutiveSummary

`agents/summarizer.py:summarize(goal, matrix, blocks, connections)`. Top findings, top connections, key gaps, matrix table.

### 9. Finalise

`orchestrator._finalize(goal, matrix, blocks, progress, corpus=…)` assembles the `Report`:

- `planner_question_type` required (see `models.Report`).
- Scenarios (`agents/scenarios.py`), assumption inversions, and block headers run in parallel.
- `save_report` writes `output/<stem>.json`; load is tolerant of missing `planner_question_type` (backfill from `matrix.question_type`).

## Second-pass operations

Same `orchestrator` module exposes:
- `deepen_cell(report, cell, focus)` — `plan_deepen` → scouts → re-analyst for one cell.
- `add_domain(report, name, layers, freetext)` — `plan_new_domain` → scouts → analyst for the new slice.
- `connect_blocks(report, cell_a, cell_b)` — single `bisociate_pair` call appended to connections.

## Export

`export.py` / `export_docx.py` / `docx_writer/` produce docx/pptx/md/json/one-pager; `api.main` exposes them via `/api/research/{id}/export/{fmt}`.

## Data contracts

All hand-offs are Pydantic v2 models in `models.py`: `Matrix`, `CellPlan`, `ScoutTask`, `ScoutResult`, `Finding`, `Block`, `Connection`, `ExecutiveSummary`, `Report`, plus `ScenarioCone`, `BlockInversions`, `ConsensusLayer`, `Doubt`, `QuantMetric`.

See `CONFIG_FLAGS.md` for environment variables and profile overrides.
