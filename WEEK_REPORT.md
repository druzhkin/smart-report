# Week-7 Report (in progress)

**Brief:** `WEEK_BRIEF_VALYU.md` (Valyu integration + Run 2 + Phase 4 prep)
**Started:** 2026-04-26 (Monday)
**Sessions to date:** 1 (this Claude Code session)

> This report grows incrementally across sessions. Each Day section is
> self-contained — pick up where the last commit left off by reading
> `daily/<n>.md` for the most recent day, then the corresponding section
> here.

---

## TL;DR (running update)

Days 1–3 mock-only. Day 4 broke v1 brief's load-bearing assumption
(Valyu proprietary ≠ EU regulatory) at ~$2.69 cost. Day 5: user
dropped **WEEK_BRIEF_v3.md** mid-session — full architectural pivot
to "Valyu-first" with hard invariant test. Day 5 closed v3 §5.1
(standard recon, $0.0105) + §3.5 (4 invariant tests) + capability
map per-domain coverage verdict. Routing matrix built but NOT yet
wired into orchestrator (separate sprint).

Test suite 551 passed (+4 Day 5 invariants). Week-to-date $2.70
of new $22.50 v3 hard cap (12% spent). Days 6-7 + extended need
for SearchBackend abstraction + Tavily/Exa clients + orchestrator
rewrite + degradation warning.

## What's done

### Day 1 (2026-04-26) ✅

- `docs/VALYU_CAPABILITY_MAP.md` — built from free MCP introspection
  + Valyu Python SDK metadata endpoints. 36 datasources enumerated
  across 10 categories with full pricing/schema. Skipped $0.25
  standard recon (decision A1).
- `docs/run2_baseline/REVIEW_q{1,2,3}.md` + 3 rendered DOCX —
  Run 2 baseline review based on yesterday's Step 3.3 acceptance
  fixtures (decision A2 — saved $7-8 vs fresh Sonnet runs).
- `BUDGET.md`, `BLOCKERS.md`, `daily/1.md` — initial scaffolding +
  end-of-day log.
- Commit: `c8c2e1e` (`docs(week-7): Day 1 — Valyu recon + Run 2 baseline review`).

### Day 2 (2026-04-26) ✅

- `smart_report/sources/valyu.py` — async ValyuClient + retry shim
  (3 attempts, 1s/2s/4s backoff, 5xx + ConnectionError + Timeout
  retried, 4xx not).
- `smart_report/sources/__init__.py` — package + exports.
- `tests/test_valyu_client.py` — 12 mocks + 1 live arXiv smoke
  (PASSED at $0.001).
- `pyproject.toml` — registered `live` pytest marker, default
  `addopts` skip.
- `BLOCKERS.md` A3 logged: `fast_mode=True` + `search_type="proprietary"`
  is API-incompatible; default fixed to `("all", fast_mode=True)`.
- Commit: `93e6665` (`feat(sources): valyu backend client + retry shim`).

### Day 3 (2026-04-26) ✅

- `smart_report/domain_detector.py` extended with `Backend` enum,
  `ValyuCallSpec`, `BackendPlan`, `BACKEND_PLAN_BY_DOMAIN`,
  `backend_plan_for(query)`. Mapping faithfully encodes brief §3.6
  onto our existing 6 QueryDomain values, with EU_REGULATORY using
  `("proprietary", fast_mode=False)` to access Valyu's value-add
  corpus and close the A3 risk.
- `smart_report/sources/orchestrator.py` — `SearchOrchestrator` with
  primary→fallback dispatch. Manual Perplexity surfaced via
  `SearchOutcome.handoff_required=True` (no auto Perplexity client
  exists yet — out of scope, surfaced as sentinel).
- `tests/test_search_orchestrator.py` — 13 tests:
  * 6 routing-decision tests (one per non-trivial domain + table-coverage)
  * 7 dispatch tests (manual handoff, EU reg kwargs, empty→fallback,
    error→fallback, RU no-fallback, no-Valyu-client paths × 2)
- Cost: $0 (mock-only).

## What's not done yet

### Day 4 (2026-04-26) ✅ closed with REGRESSION + over-spend

- `configs/ab_run2.yaml` — A/B config for Day 4-5.
- `scripts/ab_run2.py` — `--plan` + `--live` harness (in-process v4
  cycle, mirrors `live_acceptance_run.py`).
- Live Q3 EU DAC config B run (`runs/ab_run2/q3_eu_dac_B_*.json`):
  - Cost $1.58 vs baseline $0.89 (+78%, breached $1.50 sub-cap)
  - Source count 2 vs baseline 29 (-93%)
  - 0 STRONG vs baseline 64
  - **Root cause:** Valyu `proprietary` returned arxiv+pubmed for an
    EU regulatory query. Day 1 capability map flagged this; Day 3
    routing built the dependency anyway based on brief assumption.
- Operator mistake: duplicate `--live` launch wasted ~$1.10. Day 4
  total spend ~$2.69.
- Day 5 multi-query A/B HALTED per stop-condition (BLOCKERS.md A6).
- Commits: `092ebc3` (scaffolding) + Day 4 close (this commit).

### Day 5 (2026-04-26) ✅ — **v3 brief reset**

User dropped `WEEK_BRIEF_v3.md` mid-session. Architectural pivot to
"Valyu-first" with code-enforced invariants. Day 5 of original
calendar = Day 1 of v3 plan. What landed:

- `WEEK_BRIEF_v3.md` saved to repo (API keys redacted).
- `scripts/valyu_standard_recon.py` — v3 §5.1 mandatory one-shot.
  Cost $0.0105 (vs $0.25 brief estimate; Valyu prices per-result).
  Saved to `runs/valyu_recon/standard_recon_response.json` +
  `docs/VALYU_STANDARD_RECON_FINDINGS.md`.
- `docs/VALYU_CAPABILITY_MAP.md` updated with per-domain coverage
  verdict — Day 4's regression now has a documented root cause:
  Valyu has NO native eur-lex / europa dataset.
- `smart_report/sources/routing_matrix.py` — v3 §3.2 routing
  matrix as a string-keyed dict (11 domains, Valyu primary on 8
  per the architectural invariant).
- `tests/test_routing_invariants.py` — 4 tests per v3 §3.5; all pass.
  Total suite 551 passed (+4 from Day 5).
- 3 autonomous decisions logged: A8 (paths kept), A9 (matrix not
  yet wired), A10 (recon less informative than brief assumed).

**NOT yet done from v3 plan** (next sprint(s)):
- §5.6 SearchBackend Protocol abstraction
- §5.6 PerplexityBackend adapter (existing search.py wrapped)
- §5.9 Tavily client + tests + live smoke
- §5.10 Exa client + tests + live smoke (with outputSchema)
- §5.13 SearchOrchestrator rewrite (Valyu-first hybrid, augment-
  on-failure semantics)
- §3.4 / §5.15 Degradation warning surface in DOCX renderer
- §5.17-5.18 New A/B run (config A vs B per v3, Q1/Q2/Q3 × 2 = 6 runs)
- §5.20 Phase 4 brief (now load-bearing for the whole pivot)
- §5.21-5.22 Closing run + WEEK_REPORT finalisation

Brief's full A/B HALTED (A6). Two replacement options pending user
decision:

  **(a)** Re-test Q3 with `("all", fast_mode=True)` instead of
  proprietary (~$1.50). Tests whether Valyu's web tier surfaces
  europa.eu where proprietary did not. If still regression →
  full HALT, Day 5 = brief writing.

  **(b)** Skip live runs entirely on Day 5; treat Day 5 as a brief-
  writing day for Phase 4. Conservative on budget.

Per brief §3.8 + §3.9:
- `configs/ab_run2.yaml` with explicit A | B switch
- Single-query dry-run on Q3 (regulatory — strongest expected Valyu
  win). Hard cap $1.50 for the dry-run.
- Stop on first sign hybrid is worse than baseline.

### Day 5 — Full A/B run + analysis (PENDING)

6 runs total (Q1/Q2/Q3 × A/B), summary at `runs/ab_run2/SUMMARY.md`.

### Day 6 — Phase 4 brief (PENDING)

Synthesise Day 1 REVIEW + Day 5 A/B into `notion/PHASE_4_BRIEF.md`.
Candidate Steps in brief — pick by real findings.

**New input for this brief (added 2026-04-26):** Exa AI + Tavily API
keys are available locally (see `BLOCKERS.md` A4). Phase 4 brief
should weigh whether either fills a gap that Run 2 + A/B exposed in
Valyu's coverage, before committing engineering time to a 4-backend
orchestrator.

### Day 7 — Closing (PENDING)

- e2e prod-config run on Q1 (≤ $3)
- This `WEEK_REPORT.md` finalised
- Notion main-page sync

## Findings worth flagging up-front

1. **Valyu does NOT cover Russian sources.** No RU regulatory
   (Минстрой/Росстат), no RU RE, no RU automotive datasets. The
   brief routing table (`russian_market → Perplexity primary, Valyu
   n/a`) is correct. Phase 4 will need a different backend
   (e.g. specialised Rosstat / EISJS / MOEX clients) for our flagship
   Russian-domain queries.

2. **Q3 EU DAC after Phase 3 shows 96% STRONG / 0% MODERATE — degenerate
   distribution.** Not a bug (input is primary EU regulatory) but a
   structural smell: when ALL claims tag STRONG the calibration loses
   informative signal. Phase 4 candidate Step: minimum-distribution
   enforcement OR a "strong-input" detection that recalibrates rather
   than uniformly STRONG-ing.

3. **Step 3.3 self-assessed quality is working deterministically.**
   Q2 Moscow RE: RBC moved from passively-echoed STRONG (yesterday's
   Step 3.2) to honest MODERATE (Step 3.3). Vendor blogs dropped
   to WEAK. This is exactly the Run 1 finding 2 fix — the synthesizer
   no longer passively inherits input markdown's grade phrasing.

4. **No template leakage and no hardcoded 0.82 in any of the 3
   queries' output.** Old Run 1 / Phase 1 fixes held through Phase 3.

## Cumulative spend

| Day | OpenRouter | Valyu | Total | Hard cap remaining |
|---|---|---|---|---|
| Day 1 | $0.00 | $0.00 | $0.00 | $20.00 |
| Day 2 | $0.00 | $0.002 | $0.002 | $19.998 |
| Day 3 | $0.00 | $0.00 | $0.00 | $19.998 |
| Day 4 | ~$2.68 | ~$0.007 | ~$2.69 (1st run $1.58 + duplicate-launch $1.10) | $17.31 (under v1 $20 cap) |
| Day 5 | $0.00 | $0.0105 | $0.0105 (v3 §5.1 standard recon only) | $19.81 (v3 $22.50 cap) |
| Day 6 | TBD | TBD | TBD | TBD |
| Day 7 | TBD | TBD | TBD | TBD |
| **Week** | ~$2.68 | ~$0.009 | **~$2.69 so far** | $17.31 |

## Top decisions made without user

(Day 1)

1. **A1 — skipped paid Valyu standard recon.** SDK + MCP introspection
   covered the same capability surface for free. Saved $0.25.
2. **A2 — Run 2 baseline reused Step 3.3 fixtures** instead of fresh
   Sonnet "winner-config" runs. Saved $7-8. Same post-Phase-3 code
   path, Haiku model — substantively similar baseline for review
   purposes. If Sonnet output materially differs we can re-run.

(Day 2)

3. **A3 — `ValyuClient` defaults set to `("all", fast_mode=True)`**
   after the live API rejected `("proprietary", fast=True)` with
   a clear error. Day 3 routing layer overrides per-domain to
   `("proprietary", fast=False)` when targeting EU regulatory.
   Easy revert: flip the default back if we'd rather pay slightly
   more by default for always-on proprietary access.

(Day 3 — no new autonomous decisions; routing rules followed brief §3.6
mapped onto the existing 6-domain enum.)

## Top blockers for review

(none to date — Day 1 went smoothly)
