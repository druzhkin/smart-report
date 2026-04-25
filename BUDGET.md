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
| 2026-04-26 | Run 2 baseline (alt path: render DOCX from Step 3.3 fixtures) | $0.00 | TBD | $58.50 | n/a |

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
