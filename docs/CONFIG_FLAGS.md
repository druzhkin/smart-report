# Config Flags Reference

All knobs live in `config.py`. Env vars take effect at import time; profile overrides win for keys set in `DEPTH_PROFILES[depth]`.

## Depth profile keys

Active profile is published via `set_active_profile(depth_profile(depth))` and read by agents through `model_for(role)` / `profile_bool(key, default)` / `profile_str(key, default)` / `profile_int(key, default)` / `profile_list(key, default)`.

| Key | Type | Where consumed | Notes |
| --- | --- | --- | --- |
| `domains` / `layers` | tuple(min,max) | `agents/planner.py` | Matrix sizing bounds |
| `scouts_per_cell` | int | `planner` (legacy) | Ignored in corpus flow |
| `max_parallel_scouts` | int | `orchestrator._run_scouts_for_tasks` | Bounded semaphore |
| `max_parallel_analysts` | int | `orchestrator._analyze_cells` | Bounded semaphore |
| `planner_model` / `scout_model` / `analyst_model` / `mapper_model` / `bisociator_model` | str | `model_for(role)` | Profile beats env var |
| `perplexity_model` | str | `perplexity_model_for()` | `sonar` / `sonar-pro` / `sonar-deep-research` |
| `corpus_backends` | list[str] | `orchestrator._run_corpus_flow` | Subset of `[valyu, sonar_dr, gpt_researcher, openai_dr, gemini_dr]` |
| `valyu_mode` | str | `orchestrator._run_corpus_flow` → `corpus_fetch.fetch_corpus` | `fast` / `standard` / `heavy` / `max` — see `VALYU_MODE_PER_TIER.md` |
| `contrarian_enabled` | bool | `orchestrator._analyze_cells` | Runs `agents/contrarian.py` per block |
| `consensus_layer` | bool | `orchestrator._finalize` | Runs `agents/consensus.py` over `corpus.synth_reports` |
| `doubt_cycle_enabled` | bool | `orchestrator._run_doubt_cycle` | Currently scaffolded stub |
| `save_raw_corpus` | bool | finalize | Attach raw corpus to Report (debug) |
| `cost_cap_usd` | float | informational | Target ceiling, not enforced |

## Depth tier matrix

Defaults from `config.DEPTH_PROFILES`. `exhaustive` is an alias of `premium`.

| | light | standard | deep | premium |
| --- | --- | --- | --- | --- |
| Matrix size | 2-3 × 1-2 | 3-4 × 2-3 | 4-5 × 2-4 | 5-6 × 3-4 |
| `max_parallel_scouts` | 6 | 8 | 10 | 12 |
| `max_parallel_analysts` | 4 | 4 | 5 | 6 |
| `analyst_model` | gemini-2.5-flash | gemini-2.5-flash | gemini-2.5-flash | gemini-2.5-pro |
| `perplexity_model` | sonar | sonar-pro | sonar-deep-research | sonar-deep-research |
| `corpus_backends` | valyu, gpt_researcher | valyu, sonar_dr, gpt_researcher | valyu, sonar_dr, gpt_researcher | + openai_dr, gemini_dr |
| `valyu_mode` | fast | fast | standard | fast |
| `contrarian_enabled` | ✗ | ✓ | ✓ | ✓ |
| `consensus_layer` | ✗ | ✗ | ✗ | ✓ |
| `cost_cap_usd` | 1.5 | 3 | 6 | 25 |

## Intake tier aliases

`TIER_ALIASES` in `config.py`:

| Alias (frontend/intake) | Resolved depth |
| --- | --- |
| quick_take | light |
| investment_brief | standard |
| strategy_note | deep |
| full_research | exhaustive (= premium) |

Use `resolve_tier(tier_or_depth)` to normalise either form.

## Environment variables

### API keys

`OPENROUTER_API_KEY`, `PERPLEXITY_API_KEY`, `FIRECRAWL_API_KEY`, `TAVILY_API_KEY`, `CORE_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, `PUBMED_API_KEY`, `GAMMA_API_KEY`, `GAMMA_THEME_ID`, `BRAVE_API_KEY`, `JINA_API_KEY`, `PARALLEL_API_KEY`, `VALYU_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` (fallback `GOOGLE_API_KEY`).

Missing key → that backend is silently skipped at runtime.

### Pipeline switches (bool, `true`/`false`)

| Var | Default | Effect |
| --- | --- | --- |
| `USE_PERPLEXITY` | true | Enable Perplexity search |
| `USE_JINA_READER` | true | Jina reader fallback in `search.py` |
| `USE_ACADEMIC` / `USE_CHEAP_WEB` / `USE_TAVILY` | true | Legacy search backends |
| `USE_GPT_RESEARCHER` | false | Enable gpt-researcher in legacy flow |
| `USE_TAVILY_DEEP` | false | Tavily DR (legacy) |
| `USE_PARALLEL` | false | Parallel.ai DR (legacy) |
| `USE_VALYU` | false | Valyu DR (legacy + required for corpus) |
| `USE_OPENAI_DR` | false | OpenAI o3-deep-research in corpus flow |
| `USE_GEMINI_DR` | false | Gemini DR (2.5 Pro + Google Search grounding) |
| `USE_CORPUS_FLOW` | false | Master switch for Variant E |
| `USE_CONTRARIAN_PASS` | true | Legacy contrarian toggle (profile beats this) |
| `INTAKE_DIALOG_ENABLED` | true | Chat-phase Q&A before planner |

### Tuning

| Var | Default | Effect |
| --- | --- | --- |
| `CORPUS_MIN_FINDINGS_PER_CELL` | 5 | Threshold for gap-fill scouts in corpus flow |
| `CORPUS_VALYU_MODE` | fast | Baseline Valyu mode (profile overrides when set) |
| `VALYU_MODE` | standard | Legacy flow Valyu mode (`search_deep.py`) |
| `TAVILY_DEEP_MODEL` | mini | `mini`/`auto`/`pro` |
| `PARALLEL_PROCESSOR` | core | `base`/`core`/`ultra` |
| `TAVILY_INCLUDE_DOMAINS` | "" | Comma-separated whitelist |
| `OPENAI_DR_MODEL` | o3-deep-research-2025-06-26 | |
| `GEMINI_DR_MODEL` | gemini-2.5-pro | |
| `INTAKE_MODEL` | google/gemini-2.5-flash | |
| `INTAKE_MAX_TURNS` | 4 | |

### Model role defaults (profile overrides)

`PLANNER_MODEL`, `SCOUT_MODEL`, `ANALYST_MODEL`, `MAPPER_MODEL`, `BISOCIATOR_MODEL`, `PERPLEXITY_MODEL`.

### Parallelism fallbacks

Used when no depth profile is active: `SCOUTS_PER_CELL`, `MAX_PARALLEL_SCOUTS`, `MAX_PARALLEL_ANALYSTS`.

### Pricing

`CURRENCY_LABEL` (default ₽), `USD_TO_CREDITS` (default 95 ≈ ₽/USD). Per-backend `*_USD` / `*_USD_PER_*` knobs calibrate the fallback cost estimate when an SDK doesn't surface actual cost.

## Operational notes

- `USE_VALYU=true` plus a valid `VALYU_API_KEY` is required to include Valyu in either flow. Profile lists Valyu in `corpus_backends`, but `fetch_corpus` skips it if the key is missing (silent no-op).
- `USE_TAVILY` / `USE_TAVILY_DEEP` currently hit a rate-limit cap on the project's plan (see `tavily_plan_exhausted.md`). Leave off unless the plan is upgraded.
- Planner overrides: `--question-type` is CLI-only; `JobIn` does not forward it (see `api_question_type_override_not_exposed.md`).
