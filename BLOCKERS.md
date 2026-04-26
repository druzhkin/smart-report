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

### A3 — fast_mode incompatible with proprietary search_type (live finding)

**Date:** 2026-04-26 (Day 2, during live smoke test)

**Live API constraint discovered:** Valyu rejects calls with both
`fast_mode=True` and `search_type="proprietary"` — error message
"fast_mode does not support proprietary-only searches. Use
search_type 'web', 'news', or 'all'."

**Brief tension:** §1 says "fast for everything except 1× standard
recon", but §3.6 routing table directs financial_us / regulatory_eu /
medical / scientific queries to Valyu — implying access to its
proprietary corpora (SEC, FRED, PubMed, etc.). The two are
incompatible at the API level.

**Decision:** Default `ValyuClient.search()` to
`search_type="all", fast_mode=True` — compatible with API + matches
brief's "fast everywhere" intent. Day 3 routing layer will
explicitly pass `search_type="proprietary", fast_mode=False` when
domain detection routes to Valyu for its value-add datasets. The
slow proprietary path costs ~$0.005-0.020 per call (still cheap),
but we make the cost decision visible at the routing-rule level.

**Risk if wrong:** If Day 3 routing forgets the override, Valyu
"primary" calls effectively get web search overlap with Perplexity —
zero value-add. Mitigation: A/B run on Day 5 will detect this if it
happens (Q3 EU DAC config B should show meaningfully different
sources from config A; if it doesn't, routing isn't hitting
proprietary).

**Easy to revert:** flip the default back to
`search_type="proprietary", fast_mode=False` if we'd rather pay
slightly more per call by default and have the value-add corpora
always-on.

---

### A6 — HALT Day 5 multi-query A/B (Valyu hybrid regresses on Q3)

**Date:** 2026-04-26 (Day 4)

**Trigger:** First live Q3 EU DAC dry-run with config B
(`runs/ab_run2/q3_eu_dac_B_20260426T065658Z.json`) showed:
- Cost +78% vs baseline ($1.58 vs $0.89, breaching brief's $1.50 cap by $0.08)
- Source count -93% (2 vs 29)
- 0 STRONG vs 64 STRONG
- 20 WEAK vs 1 WEAK
Brief stop condition "evidence_quality drops below baseline" met
catastrophically.

**Root cause:** Valyu's `search_type="proprietary"` does NOT surface
EU regulatory primary documents. It returns arxiv + pubmed +
financial + biomed because those are the curated datasets in the
"proprietary" tier. The Day 1 capability map flagged this
("No EU regulatory dataset listed by name") but Day 3 routing built
EU_REG → Valyu proprietary anyway, on the brief's assumption that
Valyu would cover EU regulators.

**Decision:** Halt the Day 5 multi-query A/B (Q1/Q2/Q3 × {A,B}).
Running 2 more queries with the same routing would burn $3-5 just
to confirm the same negative signal.

**Risk if wrong:** None — if hybrid is actually fine on Q1 / Q2 we'd
discover that on Day 6 with a single re-test instead of a 6-query
run.

**Easy to revert:** flip Day 5 plan back to "full A/B" once routing
or backend is fixed.

---

### A7 — Operational error: duplicate --live launch (~$1.10 wasted)

**Date:** 2026-04-26 (Day 4)

**What happened:** Launched a second `--live` run for Q3 EU DAC
~30s before the completion notification arrived for the first one.
Second run reached "synthesizer second-attempt" before I killed it.
~$1.10 estimated wasted spend, no output captured.

**Root cause:** I assumed the first --live had died silently
(0-byte output file for >3 min) and re-launched, but it was just
slow-starting. Output appeared right after I launched the second
process.

**Mitigation in script for next time:** None added — the script is
fine, the operator (me) made the mistake. For future --live
invocations: check `runs/ab_run2/` for new output files AND run
`Get-Process python` before re-launching.

---

### A4 — Exa AI + Tavily keys provided, decision deferred to Day 6

**Date:** 2026-04-26 (Day 3, end of session)

**What happened:** User dropped two additional search-backend API keys
into chat (Exa AI + Tavily, Tavily also has an MCP endpoint). Neither
is in `WEEK_BRIEF_VALYU.md`'s scope.

**Decision:** Do NOT extend the Day 3 SearchOrchestrator with Exa /
Tavily backends mid-week. Reason:
1. Run 2 A/B (Day 5) is meant to validate Valyu vs baseline. Adding
   two more backends before that signal exists turns a clean A/B into
   a 4-way comparison with no statistical floor.
2. Two more backends = two more clients + retry shims + tests + a
   non-trivial expansion of the routing table. ~½ day each, spends
   the Day 4 / Day 5 slot meant for the actual Valyu A/B.
3. Day 6 Phase 4 brief is the right place to weigh Exa / Tavily
   against the Run 2 + A/B findings — by then we have evidence on
   where Valyu over-/under-delivered, which informs whether Exa
   (semantic) or Tavily (cheap web) actually fills a gap.

**Where the keys live:** `.env` (gitignored). User added them manually
because the file lives in a permission-restricted directory the agent
cannot write to. Keys are NEVER committed and never echoed to tracked
docs.

**Easy to revert:** revisit on Day 6 with full A/B results in hand,
extend the routing table + add clients in a one-day sprint. The
Day 3 `Backend` enum + `BackendPlan` shape was deliberately left
open to extension — adding `Backend.EXA` / `Backend.TAVILY` is
mechanical.

---

## Open blockers

(none currently — Day 1-3 closed)

---

## Items deferred for review

- **Exa AI + Tavily backend integration** — keys available locally,
  evaluation deferred to Day 6 Phase 4 brief. See A4.
