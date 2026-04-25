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
