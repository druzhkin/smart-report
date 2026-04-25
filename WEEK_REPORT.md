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

Days 1–3 closed in a single session at **$0.002 cumulative spend**
(one live Valyu arXiv smoke). Three autonomous decisions logged
(A1/A2/A3 in `BLOCKERS.md`). Test suite at 547 passed (+13 from
Day 3 routing tests, +12 from Day 2 client tests). Days 4–7 remain
(A/B prep + Run + Phase 4 brief + closing).

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

### Day 4 — A/B prep + Q3 dry-run (PENDING)

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
| Day 4 | TBD | TBD | TBD | TBD |
| Day 5 | TBD | TBD | TBD | TBD |
| Day 6 | TBD | TBD | TBD | TBD |
| Day 7 | TBD | TBD | TBD | TBD |
| **Week** | $0.00 | $0.002 | **$0.002 so far** | $19.998 |

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
