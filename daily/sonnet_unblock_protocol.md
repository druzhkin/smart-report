# Sonnet Unblock + Smoke Verify + §5.6 Protocol — Session 2026-04-26

## Что сделано

### Block A — Sonnet hang diagnosis ✅

Diagnostic chain (4 probes, ~$0.15 cumulative):

1. `scripts/diagnostics/sonnet_smoke.py` — minimal direct httpx call
   to Sonnet 4.6 + 4.5 + Haiku 4.5, all OK 3-5s. **Rules out
   OpenRouter outage.**
2. `scripts/diagnostics/sonnet_pipeline_smoke.py` — `call_json` with
   3k token prompt, OK 4.7s. **Rules out smart_report.llm wrapper.**
3. `scripts/diagnostics/sonnet_large_prompt_smoke.py` — 3k/30k/100k
   token prompts, all OK 3-5s. **Rules out prompt size.**
4. `scripts/diagnostics/sonnet_json_format_smoke.py` —
   `response_format=json_object` isolated and combined with longer
   output, all OK ≤16s. **Rules out structured-output as direct
   cause.**

Refactored `scripts/run2_baseline.py` to be self-contained (was
importing `COMPARISON_QUERIES` from `live_acceptance_run.py` which
monkey-patches `httpx.Response.raise_for_status` globally). Q1 EV
with monkey-patch removed STILL hung at synth → confirmed monkey-
patch hypothesis WRONG.

**Root cause (BLOCKERS.md A13):** `smart_report/synthesizer.py`
sets `max_tokens=32000`. Sonnet structured JSON gen ~37 tok/s. For
21k actual tokens → 9-15 min. Run 2 watchdogs of 10-16 min were
**killing legitimate slow generation**, not diagnosing hangs.

Commit: `a498ee0`.

### Block B — Q1 EV Sonnet baseline (partial) ⚠️

Single Q1 EV run (per task §3.1), wall time 42 min before kill at
the 30-min-extended-to-monitor-40-min watchdog. Buffered output on
kill revealed:
- PM ✓, intake ✓, analyzer ✓
- **Synthesizer first attempt SUCCEEDED** (`Финальный отчёт готов`)
- bibliography ✓
- `data_audit: critical_failure` → triggered coverage retry
- Synthesizer SECOND attempt started → killed mid-way

**A13 confirmed for ONE synth call.** A14 surfaced: data_audit
critical_failure doubles synth time (28-30 min), pushing total wall
to **~33-45 min per query**. Watchdog 30 min was still too tight.

DOCX not captured (harness saves only after coverage retry returns).
Substance verification of DOCX-rendered signals (calibration /
template / confidence) on Sonnet still **provisional**.

`docs/run2_baseline/SONNET_VERIFY.md` — partial verdict written.
`docs/run2_baseline/RUN2_FINDINGS_SUMMARY.md` — updated with the
provisional pin and A14 reference.

### Block C — Phase 4 candidate prioritization ✅

`notion/PHASE_4_PRIORITIZATION.md` — 6 candidates ranked
Impact + Cost + Risk + Synergy framework, recommended 11-session
sequence ending at Phase 4 brief itself. Top 3:

1. **RU regulatory backend** (Score 16/20) — Rosstat / CBR / MOEX
   close the biggest visible Q2 gap.
2. **DOCX render `all_sources[].reliability` with reason** (Score
   15/20) — pure-code fix, makes Step 3.3 work fully visible.
3. **Sonnet 4.6 health check + httpx hang detection** (Score 14/20) —
   promoted to top-3 because A13 confirms operational urgency.

Tavily / Exa / outputSchema / cross-backend dedup deferred to Phase 5
with explicit rationale.

Commit: `e26ee4f`.

### Block D — §5.6 SearchBackend Protocol + Perplexity adapter ✅

- `smart_report/sources/base.py` — Protocol + Source / Finding /
  SearchResult / CostEstimate dataclasses. `runtime_checkable`.
- `smart_report/sources/perplexity_adapter.py` — wraps existing
  `smart_report.search.search()` (v3-era), maps to SearchResult.
  **Zero behaviour change** in underlying function.
- `tests/sources/test_base.py` — 6 dataclass + Protocol invariants.
- `tests/sources/test_perplexity_adapter.py` — 9 behaviour-
  preservation + adapter contract tests.

Critical invariants preserved:
- Adapter NEVER pre-grades sources (`quality_tier=None`) — Step 3.3
  classifier owns it.
- Multiple findings citing one URL → 1 Source instance (identity).
- Exceptions surface via `SearchResult.error` flag, NOT propagated.

`is_primary_capable=False` per v3 §0 invariant.

Total suite: **566 passed** (+15 from Block D), 0 regressions,
invariant test still green.

Commit: `9b80197`.

### Block E — Closing ✅

This file. Suite re-check + final push.

## Sonnet diagnosis result

**Resolved at protocol level.** `max_tokens=32000` × ~37 tok/s
generation rate on Sonnet 4.6 structured JSON = 9-15 min per synth
call. With data_audit coverage retry, **2× synth = 28-30 min**.
Total wall time per query: 33-45 min minimum.

**No pipeline change required.** Operational fix:
- Watchdog windows for Sonnet runs ≥ 45 min per query.
- For multi-query A/B (3 queries), allocate 3-4 hours wall clock.
- Phase 4 candidate (Step #3 in PHASE_4_PRIORITIZATION): emit
  bytes-received progress events so harness can distinguish
  "generating" from "stuck", and stop guessing wall-clock timeouts.

## Substance verification result

- **Pipeline completion on Sonnet:** ✅ confirmed (Q1 first synth
  succeeded).
- **DOCX-rendered substance signals:** still provisional
  (Day-1 Haiku-fixture verdict). Needs:
  - A future session with ≥45 min/query watchdog, OR
  - One-line harness change to render DOCX after first synth event
    (before coverage retry starts) — surfaces as future Phase 4
    candidate alongside Step #3.

## Phase 4 priority order

Per `notion/PHASE_4_PRIORITIZATION.md`. Top 3 + sequence laid out;
items 4-6 + deferred Phase 5 also documented. Sequence:

1. §5.6 Protocol (this session)
2. §5.7 Valyu adapter (next session)
3. RU regulatory backend (then)
4. §5.13 Orchestrator wire-up (then)
5. DOCX reliability rendering
6. LLM observability (Step #3 in priority)
7. A/B run
8. evidence_gaps post-synth
9. untagged claims audit
10. regulatory_eu degradation observability
11. Phase 4 brief itself

## §5.6 Protocol status

✅ Done. Protocol + Perplexity adapter + 15 tests, all green.
Foundation in place for §5.7 Valyu adapter next session.

## Сколько потрачено

| Item | Cost |
|---|---|
| Block A 2.1 — minimal smoke (3 models) | $0.003 |
| Block A 2.2 — pipeline call_json smoke | $0.003 |
| Block A 2.2 — large-prompt threshold probe (3 sizes) | $0.14 |
| Block A 2.2 — response_format probe (3 cases) | $0.04 |
| Block A 2.2 — Q1 EV with monkey-patch removed (Q1 attempt 2) | ~$0.40 |
| Block B — Q1 EV Sonnet baseline (first synth completed) | ~$2.50 |
| Block C — Phase 4 prioritization | $0 |
| Block D — §5.6 Protocol + tests | $0 |
| **Session total** | **~$3.10** |

| Cap | Spent | Remaining |
|---|---|---|
| Session OpenRouter ($7) | ~$3.10 | ~$3.90 (56% headroom) |
| Backends ($0) | $0 | $0 |
| Week-to-date (v3 $22.50) | ~$8.35 | ~$14.15 (63% headroom) |

## Что в очереди на следующую сессию

Per task §10 priority order + PHASE_4_PRIORITIZATION sequence:

1. **§5.7 Valyu adapter** — wrap existing `ValyuClient` to implement
   `SearchBackend` Protocol. Mock-only, $0.
2. **OPTIONAL pre-§5.7:** add the one-line harness checkpoint fix
   (render DOCX after first synth event) so a single Q1 EV re-run
   captures Sonnet DOCX for true substance verification. Cost
   $2.50 + 45 min wall.
3. After §5.7 Valyu: RU regulatory backend (#1 in PHASE_4_PRIORITIZATION),
   2-3 sessions, $0-0.05.
4. After RU backend: §5.13 Orchestrator rewrite with augment-on-
   failure semantics + degradation_warning. ~$0.50 testing.

## Push status

5 commits this session:
- `a498ee0` — fix(diagnosis): sonnet 4.6 v4-cycle hang root cause
- `e26ee4f` — docs(phase4): candidate step prioritization
- `9b80197` — feat(sources): SearchBackend protocol + perplexity adapter
- (this commit) — chore: closing day report + A14 + verdict updates
