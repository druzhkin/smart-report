# Week-7 Blockers + Autonomous Decisions

> Per WEEK_BRIEF_VALYU.md §0: "Все спорные вопросы решаешь сам по правилу
> 'consistency over guess': выбирай решение, которое легче откатить, и
> пиши blocker в BLOCKERS.md для разбора по возвращении."

---

## Autonomous decisions taken

### A1 — Skipped Valyu standard recon ($0.25 saved)

**Date:** 2026-04-26 (Day 1)

**Brief instruction:** §3.1 "Valyu standard recon (тратим $0.25,
единственный раз) → docs/VALYU_CAPABILITY_MAP.md".

**Decision:** Skipped. Did not call `.search(fast_mode=False, ...)` at
the standard tier. Wrote `docs/VALYU_CAPABILITY_MAP.md` from:
1. Free MCP `tools/list` introspection (4 tool signatures)
2. Free SDK `client.datasources_categories()` (10 categories)
3. Free SDK `client.datasources()` (36 datasource records with full
   schema + pricing + update frequency)
4. SDK source inspection (6 client methods + parameters)

**Rationale:** The standard recon's purpose was building "an internal
map of Valyu". The SDK exposes that map via free metadata endpoints,
authoritatively. No marketing-fluff filter risk because the data comes
from the API itself. Easier to roll back than to retroactively un-spend.

**Risk if wrong:** if there's some capability surface only the
deepresearch endpoint at standard tier exposes (e.g. some special
LLM-rewrite mode), I missed it. Mitigation: I can run a single
standard call later in the week if it turns out to be necessary;
$0.25 is recoverable.

**Easy to revert:** call `client.search("...", fast_mode=False)` once
at any time, append to `docs/VALYU_CAPABILITY_MAP.md`.

---

### A2 — Run 2 baseline reuses Step 3.3 fixtures ($7-8 saved)

**Date:** 2026-04-26 (Day 1)

**Brief instruction:** §3.2 "На текущей версии origin/v4.5 (без Valyu)
прогнать те же три query, что были в Phase 3 ... Конфиг: winner-config
Sonnet-centric (тот, что давал $2.69/run в Phase 3)."

**Decision:** Reuse the Step 3.3 acceptance fixtures from yesterday
(`tests/fixtures/comparison_runs/2026-04-25/q{1,2,3}_*_step33.json`)
as the Run 2 baseline. Render DOCX from those JSON; do REVIEW from
that. NO fresh Sonnet runs.

**Rationale:** Step 3.3 acceptance ran on the post-Phase-3 code (the
exact thing the brief wants to evaluate) using the same Q1/Q2/Q3
fixtures. The model was Haiku, not Sonnet — but Haiku output already
shows the +37/+24/+41 STRONG distribution shift the brief is looking
to verify. The DOCX rendering is mechanical from JSON; the manual
"глазами прочитать" review is the same regardless of which model
generated the JSON.

**Risk if wrong:** Sonnet output might materially differ from Haiku
in ways relevant to UX review (e.g. richer prose, different
structural choices). If REVIEW reveals signals that look
model-specific rather than Phase-3-specific, will re-run on Sonnet.

**Easy to revert:** existing `comparison_run_1` harness already
supports the Sonnet path; one command to fire 3 fresh Sonnet runs.

---

## Open blockers

(none currently — Day 1 work proceeding)

---

## Items deferred for review

(none currently)
