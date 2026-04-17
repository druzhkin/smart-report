# Valyu Mode per Depth Tier

Valyu DeepResearch runs in four tiers (`fast` / `standard` / `heavy` / `max`).
The two flows pick the mode differently, which matters for both cost and
source coverage.

## Summary

| depth | corpus flow (`USE_CORPUS_FLOW=true`) | legacy flow (`search_deep.valyu_research`) |
| --- | --- | --- |
| light / quick_take | fast → $0.10 | env `VALYU_MODE` (default `standard` → $0.50) |
| standard / investment_brief | fast → $0.10 | env `VALYU_MODE` (default `standard` → $0.50) |
| deep / strategy_note | **standard → $0.50** | env `VALYU_MODE` (default `standard` → $0.50) |
| premium / full_research / exhaustive | fast → $0.10 | env `VALYU_MODE` (default `standard` → $0.50) |
| no active profile | `CORPUS_VALYU_MODE` (default `fast`) | env `VALYU_MODE` (default `standard`) |

Pricing per call is Valyu-published (see `corpus_fetch.py:_fetch_valyu`
docstring): `fast` $0.10, `standard` $0.50, `heavy` $2.50, `max` $15.

## Wiring

| Flow | File:line | How mode is chosen |
| --- | --- | --- |
| Corpus (orchestrator → fetch_corpus) | `orchestrator.py:335` | `profile_str("valyu_mode", settings.corpus_valyu_mode)` |
| Corpus (fetch_corpus signature default) | `corpus_fetch.py:724` | `valyu_mode: str = "fast"` |
| Corpus (per-profile defaults) | `config.py` DEPTH_PROFILES | `valyu_mode` key in each tier |
| Corpus (env fallback) | `config.py:222` | `CORPUS_VALYU_MODE`, default `fast` |
| Legacy | `search_deep.py:212` | `mode = settings.valyu_mode or "standard"` — **no profile override** |
| Legacy env | `config.py:237` | `VALYU_MODE`, default `standard` |

## Cost-compare caveats

- **Legacy is always `standard` by default.** Cost comparisons "legacy Valyu
  line is 5× corpus" usually reflect the mode gap, not call volume.
- **Fast-mode accounting can lie.** Valyu sometimes omits `cost` in the
  response for `fast`; the logger then falls back to
  `settings.valyu_usd_per_query` (env `VALYU_USD`, default `0.50`), inflating
  fast-mode totals by 5×. Verify `result.cost` before reading ₽ numbers.
- **For A/B benchmarking**, either set `VALYU_MODE=fast` in `.env` before
  legacy runs, or spell out "legacy standard vs corpus fast" in the write-up.

## Override tips

- One-off: `CORPUS_VALYU_MODE=heavy python cli.py ...` (applies when profile
  doesn't set `valyu_mode`, which none of the current tiers do).
- Per-profile change: edit `DEPTH_PROFILES[depth]["valyu_mode"]` in `config.py`.
- Legacy flow: only `VALYU_MODE` env — no profile plumbing exists today.

## Change protocol

When tier defaults change, sync **all three**:
1. `config.py` DEPTH_PROFILES.
2. `docs/CONFIG_FLAGS.md` depth-tier matrix.
3. This file and `docs/PIPELINE_OVERVIEW.md` depth-tier table.
