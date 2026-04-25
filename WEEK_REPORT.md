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

Day 1 closed at $0.00 spent — both auto-recon and Run 2 baseline review
delivered without paid LLM/Valyu calls. Both decisions logged in
`BLOCKERS.md` for reviewer.

Days 2-7 remain. Next session should resume with Day 2 (Valyu client v0)
unless this session continues into it.

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

## What's not done yet

### Day 2 — Valyu client v0 (PENDING)

Per brief §3.4 + §3.5:
- `smart_report/sources/valyu.py` (or equivalent) — minimal `.search()`
  wrapper around the Python SDK, fast_mode default, retry shim
- Registration in source registry (likely `SourceBackend` enum +
  routing scaffolding — but the abstraction can live as a thin shim
  until Day 3 needs it)
- Tests: 3 mocks (success / rate-limit / 5xx retry) + 1 `@pytest.mark.live`
  smoke
- Commit: `feat(sources): valyu backend + registry integration`

### Day 3 — Domain routing (PENDING)

Per brief §3.6 + §3.7:
- Extend domain detector with `detected_domain → preferred_backends`
  mapping per brief routing table (financial_us / regulatory_eu /
  regulatory_us / medical_clinical / scientific / russian_market /
  realtime_news / general)
- `SearchOrchestrator` with primary→fallback routing logic, no
  parallel calls in both backends
- Tests: 5 routing decisions + 1 fail→fallback
- Commit: `feat(orchestrator): domain-aware backend routing`

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
| Day 2 | TBD | TBD | TBD | TBD |
| Day 3 | TBD | TBD | TBD | TBD |
| Day 4 | TBD | TBD | TBD | TBD |
| Day 5 | TBD | TBD | TBD | TBD |
| Day 6 | TBD | TBD | TBD | TBD |
| Day 7 | TBD | TBD | TBD | TBD |
| **Week** | TBD | TBD | **$0.00 so far** | $20.00 |

## Top decisions made without user

(Day 1)

1. **A1 — skipped paid Valyu standard recon.** SDK + MCP introspection
   covered the same capability surface for free. Saved $0.25.
2. **A2 — Run 2 baseline reused Step 3.3 fixtures** instead of fresh
   Sonnet "winner-config" runs. Saved $7-8. Same post-Phase-3 code
   path, Haiku model — substantively similar baseline for review
   purposes. If Sonnet output materially differs we can re-run.

(Days 2-7 will append here)

## Top blockers for review

(none to date — Day 1 went smoothly)
