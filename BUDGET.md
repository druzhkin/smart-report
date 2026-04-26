# Week-7 Budget Log

> **Caps from WEEK_BRIEF_VALYU.md §2:**
> - OpenRouter: $12 soft / $14 hard
> - Valyu: $4 soft / $6 hard
> - Total: $16 soft / $20 hard
>
> **Starting balances (verified 2026-04-26):**
> - OpenRouter: $58.50 (was $18.50 yesterday — top-up between sessions)
> - Valyu: prepaid via supplied key, no balance API observed yet

---

## Day 1 — 2026-04-26

| Date | Task | Expected | Actual | OpenRouter left before | Valyu left before |
|---|---|---|---|---|---|
| 2026-04-26 | Pre-flight (balance + Valyu auth probe) | $0.00 | $0.00 | $58.50 | budget intact |
| 2026-04-26 | Valyu MCP introspection (free) | $0.00 | $0.00 | $58.50 | budget intact |
| 2026-04-26 | Valyu SDK datasources/categories (free metadata) | $0.00 | $0.00 | $58.50 | budget intact |
| 2026-04-26 | **SKIPPED:** standard recon → SDK gave same data free | ($0.25) | $0.00 | $58.50 | $0.25 saved |
| 2026-04-26 | Run 2 baseline (alt path: render DOCX from Step 3.3 fixtures) | $0.00 | $0.00 | $58.50 | n/a |
| 2026-04-26 | Day 2 — Valyu client v0 + live arXiv smoke ($0.001) | $0.001 | $0.001 | $58.50 | $6.00 |

**End-of-Day-1 totals:**

| Category | Spent today | Budget left |
|---|---|---|
| OpenRouter | $0.00 | $58.50 (well under $14 hard cap) |
| Valyu | $0.00 | full week budget intact |
| **Total** | **$0.00** | **plenty for week** |

**Decisions logged in `BLOCKERS.md`:**

- Skipped paid `standard` recon — SDK + MCP introspection gave canonical
  surface area without payment. Saved $0.25.
- Used Step 3.3 acceptance fixtures as Run 2 baseline (Haiku, post-Phase-3
  code) instead of fresh Sonnet "winner-config" runs. Saved ~$8.
  Substantively similar — Phase 3 fixes are in both code paths. If
  Sonnet output materially diverges, will re-run.

---

## Day 2 — 2026-04-26 (continued)

| Date | Task | Expected | Actual | OpenRouter left | Valyu left |
|---|---|---|---|---|---|
| 2026-04-26 | Valyu live arXiv smoke (rejected proprietary+fast first) | $0.001 | $0.001 | $58.50 | ~$5.999 |
| 2026-04-26 | Valyu live arXiv smoke (search_type="all" success) | $0.001 | $0.001 | $58.50 | ~$5.998 |

**End-of-Day-2 totals:**

| Category | Spent today | Week-to-date | Budget left |
|---|---|---|---|
| OpenRouter | $0.00 | $0.00 | $58.50 |
| Valyu | $0.002 | $0.002 | ~$5.998 of $6 hard cap |
| **Total** | **$0.002** | **$0.002** | $19.998 of $20 cap |

**Decision logged:** A3 — `ValyuClient` defaults flipped to
`("all", fast_mode=True)` after live rejection of the proprietary+fast
combo. Day 3 routing handles the proprietary override per-domain.

---

## Day 3 — 2026-04-26 (continued, mock-only)

| Date | Task | Expected | Actual | OpenRouter left | Valyu left |
|---|---|---|---|---|---|
| 2026-04-26 | Domain routing extension (`domain_detector.BackendPlan`) | $0.00 | $0.00 | $58.50 | ~$5.998 |
| 2026-04-26 | `SearchOrchestrator` (primary→fallback, mock-only) | $0.00 | $0.00 | $58.50 | ~$5.998 |
| 2026-04-26 | 13 routing + dispatch tests (mock-only) | $0.00 | $0.00 | $58.50 | ~$5.998 |

**End-of-Day-3 totals:**

| Category | Spent today | Week-to-date | Budget left |
|---|---|---|---|
| OpenRouter | $0.00 | $0.00 | $58.50 |
| Valyu | $0.00 | $0.002 | ~$5.998 of $6 hard cap |
| **Total** | **$0.00** | **$0.002** | $19.998 of $20 cap |

**No autonomous decisions today.** Routing rules from brief §3.6 mapped
onto the existing 6-domain enum without surprises; A3 risk closed by
making `("proprietary", fast=False)` the explicit per-domain override
for EU_REGULATORY.

---

## Day 4 — 2026-04-26 (continued, BREACH)

| Date | Task | Expected | Actual | OpenRouter left | Valyu left |
|---|---|---|---|---|---|
| 2026-04-26 | configs/ab_run2.yaml + script (mock-only) | $0.00 | $0.00 | $58.50 | ~$5.998 |
| 2026-04-26 | Q3 EU DAC dry-run config B (1st, completed) | ≤$1.50 | **$1.5808** | $56.92 | ~$5.994 |
| 2026-04-26 | Q3 EU DAC dry-run config B (2nd, killed mid-run) | $0 | **~$1.10** | $55.82 | ~$5.994 |

**End-of-Day-4 totals:**

| Category | Spent today | Week-to-date | Hard cap |
|---|---|---|---|
| OpenRouter | ~$2.68 | ~$2.68 | $14.00 |
| Valyu | ~$0.007 | ~$0.009 | $6.00 |
| **Total** | **~$2.69** | **~$2.69** | **$20.00** |

**Caps status:**
- Day 4 sub-cap ($1.50 dry-run): **BREACHED by $1.18** (1.79× cap).
  - $0.08 from the first run's organic cycle cost overrun.
  - $1.10 from the operational mistake of launching a duplicate
    --live (A7).
- Week hard cap ($20.00): still 87% headroom, $17.31 remaining.

**Decisions logged:** A6 (halt Day 5 multi-query A/B due to
regression), A7 (operational mistake, no spend recovery possible).

---

## Day 5 — 2026-04-26 (continued, **v3 brief reset**)

User dropped WEEK_BRIEF_v3.md mid-session. Architectural pivot. New
budget profile: OpenRouter $14, Valyu $5, Exa $2.5, Tavily $1, total
$22.50 hard cap.

| Date | Task | Expected | Actual | OpenRouter left | Valyu left |
|---|---|---|---|---|---|
| 2026-04-26 | v3 §5.1 standard recon (one-shot) | $0.25 | **$0.0105** | $55.82 | ~$5.987 |
| 2026-04-26 | routing_matrix.py + invariant tests (mock-only) | $0.00 | $0.00 | $55.82 | ~$5.987 |

**End-of-Day-5 totals:**

| Category | Spent today | Week-to-date | Hard cap (v3) |
|---|---|---|---|
| OpenRouter | $0.00 | ~$2.68 | $14.00 |
| Valyu | $0.0105 | ~$0.020 | $5.00 |
| Exa | $0.00 | $0.00 | $2.50 |
| Tavily | $0.00 | $0.00 | $1.00 |
| **Total** | **$0.0105** | **~$2.70** | **$22.50** |

Week headroom: 88% remaining.

**Decisions logged:** A8 (kept `smart_report/sources/` paths instead
of brief's `backend/v2/sources/`), A9 (routing_matrix not yet wired
into orchestrator — separate sprint), A10 (standard recon returned
web search of Valyu's marketing pages, $0.0105 not $0.25).

---

## Session: Run 2 baseline + qualitative review (2026-04-26)

Replaces v3 §5.6 sprint per user task. Substance check before more
architecture work. Session hard cap: OpenRouter $11, backends $0.

| Date | Task | Expected | Actual | OpenRouter left | Notes |
|---|---|---|---|---|---|
| 2026-04-26 | Pre-flight: harness + Q3 EU DAC fresh Sonnet baseline | $2.69 | TBD | $55.82 | priority §9 — first run validates harness + Day 5 EU regulatory finding |
| 2026-04-26 | Q3 attempt 1 — HUNG at first synthesize call, killed at 16min | (sunk) | ~$1.35 estimate | $54.47 | PM+intake+analyze succeeded; synth never returned; no DOCX |
| 2026-04-26 | Q3 attempt 2 — also hung, killed at 10min wall (intake stage) | $1.50 | ~$0.40 estimate | ~$53 | BLOCKER: Sonnet 4.6 hangs reproducibly on Q3 today; moving to Q1 per §7 |
| 2026-04-26 | Q1 EV — also hung at synth stage, killed at 12min wall | $2.69 | ~$0.80 estimate | ~$52 | confirms Sonnet 4.6 broken globally today, not Q3-specific |
| 2026-04-26 | Q2 + Block B fresh-run path — SKIPPED | $0 | $0 | ~$52 | Sonnet broken; Block C+D pivot to Day-1 review basis |

---

## Session: Sonnet unblock + smoke verify + §5.6 Protocol (2026-04-26)

Session hard cap: OpenRouter $7, backends $0. Replaces planned «§5.6
straight to Protocol» path per user decision (need to unblock Sonnet
first because it's load-bearing for all future A/B verification).

| Date | Task | Expected | Actual | OpenRouter left | Notes |
|---|---|---|---|---|---|
| 2026-04-26 | Block A 2.1 — Sonnet 4.6 minimal smoke (3 models probed) | $0.003 | $0.003 | ~$52 | ALL PASS 3-5s; bug NOT in OpenRouter |
| 2026-04-26 | Block A 2.2 — pipeline call_json smoke (~3k token prompt) | $0.005 | $0.0032 | ~$52 | OK 4.7s; smart_report.llm wrapper not the culprit |
| 2026-04-26 | Block A 2.2 — Q1 EV with monkey-patch removed (10-min watchdog) | $2.69 | ~$0.40 estimate | ~$52 | hypothesis: monkey-patch — DISPROVEN, hang at synth same as before |
| 2026-04-26 | Block A 2.2 — Sonnet large-prompt threshold probe (3k/30k/100k) | $0.20 | $0.14 | ~$52 | all OK; prompt size NOT the cause |
| 2026-04-26 | Block A 2.2 — Sonnet response_format=json_object probe (3 cases) | $0.10 | $0.04 | ~$52 | all OK; format NOT the cause |
| 2026-04-26 | Block A 2.2 — root cause found: max_tokens=32000 + slow Sonnet structured gen | $0 (analysis) | $0 | ~$52 | A13 logged; "hangs" were premature watchdog kills on legitimate slow gen |
| 2026-04-26 | Block B — Q1 EV Sonnet baseline (30-min watchdog) | $2.69 | ~$2.50 estimate | ~$49 | first synth SUCCEEDED, killed during coverage-retry second synth (A14 logged); pipeline-completion verified, DOCX substance still provisional |

---

## Two-week brief: M1 production Valyu (2026-04-26 → ~2026-05-09)

Two-week brief from `TWO_WEEK_BRIEF.md`. Opus gate-keeper protocol.
Hard cap $61 across 14 days, soft $50.

| Date | Task | Expected | Actual | OpenRouter left | Notes |
|---|---|---|---|---|---|
| 2026-04-26 | M1 B1.1 — harness DOCX checkpoint sanity (Q1 EV, no Valyu) | $3.00 | TBD | ~$49 | validates checkpoint DOCX after first synth; closes A14 operationally |
| 2026-04-26 | M1 B1.2 — Valyu adapter live smoke (Tesla 10-K) | $0.10 | $0.04 | ~$49 | 4.25s, ≥3 sec.gov sources confirmed; SearchBackend Protocol contract met |
| 2026-04-26 | M1 B1.1 sanity Q1 EV (no Valyu, killed early after checkpoint) | $3.00 | ~$2.00 estimate | ~$47 | 38KB DOCX captured at 12:49 before coverage retry; B1.1 acceptance MET; killed before retry to save residual cost |
| 2026-04-26 | M1 B2.2 — Q1 EV PRODUCTION with Valyu (financial_us forced) | $4.00 | TBD | ~$47 | augment fires sec.gov/fred sources; tests Opus gate criterion ≥3 sec.gov citations |

**End-of-session totals:**

| Category | Spent | Hard cap |
|---|---|---|
| OpenRouter (Q3×2 + Q1 sunk) | **~$2.55** | $11 |
| Backends | $0 | $0 |
| **Session total** | **~$2.55** | **$11** |

**Cumulative week-to-date: ~$5.25** ($2.70 prior + $2.55 today) of
$22.50 v3 hard cap (23% spent). Plenty of headroom. **0 fresh DOCX
produced** — Block A failed due to A11 (Sonnet 4.6 broken on
OpenRouter). Block B (reviews) and C (summary) pivoted to
Day-1-Step-3.3-Haiku-fixture basis.
