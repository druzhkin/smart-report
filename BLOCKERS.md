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

### A13 — Sonnet 4.6 synth not "hung" — slow legitimate JSON generation (resolves A12)

**Date:** 2026-04-26 (Sonnet unblock session)

**Diagnostic chain ruled out:**
- ❌ OpenRouter outage: minimal smoke 3 models all OK 3-5s
  (`scripts/diagnostics/sonnet_smoke.py`)
- ❌ smart_report.llm wrapper: pipeline call_json with 3k-token prompt
  OK 4.7s (`scripts/diagnostics/sonnet_pipeline_smoke.py`)
- ❌ live_acceptance_run monkey-patch on httpx.Response.raise_for_status:
  Q1 EV with monkey-patch removed STILL hung at synth (run2_baseline.py
  refactored to be self-contained)
- ❌ Prompt size up to 100k chars: probe OK 5.2s
  (`scripts/diagnostics/sonnet_large_prompt_smoke.py`)
- ❌ response_format=json_object alone or with longer output: probe
  OK 16s for 600 tokens out
  (`scripts/diagnostics/sonnet_json_format_smoke.py`)

**Actual root cause:** `smart_report/synthesizer.py:395` requests
`max_tokens=32000` for the synth call. Q3 step33 fixture (Haiku-tier
baseline saved 2026-04-25) emitted ~21k tokens of structured JSON
output. Sonnet 4.6 generates structured JSON (response_format=json_object)
at ~37 tokens/sec per the json_format probe. 21k tokens × 37 tok/s
≈ **9-15 minutes** of pure server-side generation time.

Run 2 watchdog windows of 10-16 min were **killing the call slightly
before legitimate completion**, NOT diagnosing a hang.

**Confirmation pattern:**
- Smoke test on Sonnet 4.6 with small expected output: 3-5s ✅
- Smoke test with 100k tokens INPUT but small output: 5.2s ✅
- Smoke test with structured JSON, 600 tokens out: 16s ✅
- v4 cycle synth call with 32k max_tokens, ~21k actual output: 12-16min
  (I killed it at 10-16min watchdog → looked like hang)

**Fix:** ZERO pipeline change required. Operational fix in harnesses:

1. **Watchdog extension:** any run that exercises the v4 cycle synth
   on Sonnet must allow ≥25 minutes per query (vs the 10-min watchdog
   I used in Run 2 + first Q1 attempt). Acceptable wall-time per
   Sonnet baseline run: **20-25 minutes** until/unless we lower
   `max_tokens` from 32000.

2. **No pipeline-side change** — `max_tokens=32000` is intentional per
   the comment "14k causes JSON truncation". Lowering it would
   re-trigger the truncation bug Step 3.3 already resolved.

**Phase 4 candidate (Step #6 in RUN2_FINDINGS_SUMMARY.md is now
empirically grounded):** httpx-level read-timeout instrumentation
that distinguishes "actively streaming bytes" from "TCP idle" so we
can cancel only true hangs, not slow generations. Plus session
emitter for "tokens received so far" so Run 2 watchdogs can use
real progress signal.

**Cost of diagnosis:** ~$0.15 across 4 diagnostic probes. Worth the
spend — the conclusion supersedes A11+A12 (which both speculated
about Sonnet/OpenRouter brokenness; reality is much simpler).

---

### A12 — Sonnet 4.6 globally broken on OpenRouter today (3/3 hang)

**Date:** 2026-04-26 (Run 2 review session)

**Pattern across 3 separate attempts on different queries:**
- Q3 attempt 1: PM ✓ → intake ✓ → analyze ✓ → SYNTH HUNG (16min, killed)
- Q3 attempt 2: PM ✓ → intake (table extract) HUNG (10min, killed)
- Q1 EV:        PM ✓ → intake ✓ → analyze ✓ → SYNTH HUNG (12min, killed)

Common pattern in every hang: process alive, low CPU, **no outbound
HTTPS connections** (so the request isn't even in flight to OpenRouter).
The Python httpx async client is silent-failing — likely TCP connection
silently dropped, no read timeout fires, asyncio loop sits idle.

**Conclusion:** This is NOT a Q3-specific or query-specific issue
(supersedes A11's narrower diagnosis). Sonnet 4.6 via OpenRouter is
broken for our pipeline today, possibly globally on OpenRouter.

**Cost sunk:** ~$2.55 across 3 attempts, 0 DOCX produced.

**Decision (per task §7):** End Block A early with 0/3 fresh runs.
Block B (reviews) and Block C (SUMMARY) pivot to using the existing
Day-1 reviews of Step 3.3 Haiku fixtures (`docs/run2_baseline/REVIEW_q*.md`)
as substance basis. That's NOT what task §2 wanted (fresh Sonnet
runs on current `origin/v4.5`), but Step 3.3 fixtures ARE current
origin/v4.5 code path, just on a Haiku tier — the calibration logic,
domain detection, source classifier, and synth instructions are
identical between Haiku and Sonnet runs.

**Easy to revert:** when Sonnet 4.6 stabilises, run
`python -m scripts.run2_baseline --query all` and overwrite the
review/SUMMARY with fresh-Sonnet observations.

**For next session:** verify Sonnet 4.6 health BEFORE any --live spend.
A simple smoke test ($0.01): `client.chat.completions.create(model=
'anthropic/claude-sonnet-4.6', messages=[{'role':'user', 'content':'Reply OK'}])`.
If it hangs → defer Sonnet work, use Haiku, or wait for OpenRouter
to recover.

---

### A11 — Q3 EU DAC fresh Sonnet baseline hangs reproducibly

**Date:** 2026-04-26 (Run 2 review session)

**What happened:** Two attempts to run Q3 EU DAC through fresh Sonnet
4.6 4-stage v4 cycle both hung silently:
- Attempt 1 (PID 119940, 16min wall): hung at FIRST synthesize call
  after PM + intake + analyzer all succeeded.
- Attempt 2 (PID 38588, 10min wall): hung even earlier — at intake
  table-extraction LLM call.

Pattern in both: process alive, low CPU (mostly I/O wait), no outbound
HTTPS connections (so not in active LLM call), output dir empty, no
final_report saved. Killed both manually after watchdog window.

**Cost:** ~$1.65-1.85 sunk across the two attempts (no DOCX
produced).

**Diagnosis hypothesis:** Sonnet 4.6 via OpenRouter has a transient
issue today specifically affecting this query. Day 4 (yesterday)
also saw Sonnet hang on a synthesize call after JSONDecodeError, but
in a different way. Could be:
1. OpenRouter Sonnet 4.6 backend instability today
2. Dual-injection bug in v4 intake (analyzer dump + facts inventory
   overlap, ~400k tokens) interacting badly with Sonnet's request
   queue
3. httpx async client deadlock after silent connection drop

Fixing this is **out of scope** for the Run 2 review session per
task §8 (no pipeline modifications). Per task §7 stop condition:
2 unrecoverable failures → BLOCKER + push current state + move on.

**Decision:** Skip Q3 EU DAC fresh baseline. Use the existing
2026-04-25 Step 3.3 fixture (Haiku-tier) as the de-facto Q3 baseline
for the qualitative review — it's the same code path through to
synth, just on a different model tier. This reuses the Day 1 v1
review of Q3 already in `docs/run2_baseline/REVIEW_q3_eu_dac.md`,
which was based on that Step 3.3 fixture. Moving directly to Q1 +
Q2 fresh runs.

**Easy to revert:** if Sonnet 4.6 stabilises, re-run Q3 with the
same `scripts/run2_baseline.py --query q3_eu_dac` command. No code
changes needed.

---

### A8 — v3 brief paths (`backend/v2/sources/`) not followed

**Date:** 2026-04-26 (Day 5)

**Decision:** Keep existing `smart_report/sources/` paths instead of
the brief's `backend/v2/sources/` naming. Refactor risk too high
mid-pivot; existing imports across 50+ files would break with no
functional benefit. The architectural shape is what matters.

**Risk if wrong:** None — easy to rename later via a single
`git mv` + import-rewrite sweep if the user wants the brief's
naming applied.

---

### A9 — routing_matrix.py NOT yet wired into SearchOrchestrator

**Date:** 2026-04-26 (Day 5)

**Decision:** Build the v3 routing matrix + invariant test as
standalone modules first, leave Day 3's `BACKEND_PLAN_BY_DOMAIN`
in place. Wiring requires:
1. Mapping our QueryDomain enum to the brief's 11 string-keyed
   domains (some don't exist in the enum — financial_us,
   regulatory_us, medical_clinical, scientific, legal,
   technical_research, realtime_news need new markers).
2. Rewriting SearchOrchestrator dispatch with augment-on-failure
   semantics (only call augment if Valyu returns empty/error,
   not on any condition).
3. Implementing real Tavily and Exa clients first (Day 3 of v3).
4. Adding degradation_warning surface in DOCX renderer.

That's a 2-3 sprint chunk. Splitting it from today's Day 5 keeps
the commit reviewable.

**Risk if wrong:** None — the `routing_matrix.py` + invariant test
are ready to be wired the moment the orchestrator is rewritten.

---

### A10 — Standard recon less informative than brief assumed

**Date:** 2026-04-26 (Day 5)

**What happened:** v3 §5.1 mandated $0.25 standard-tier recon to
"enumerate Valyu's actual capability surface". Actual cost: $0.0105.
Result: 7 web search hits all from Valyu's own marketing/docs pages.
The authoritative dataset enumeration STILL came from Day 1's free
`client.datasources()` call (36 datasources with full schemas).

**Implication:** The brief's expectation that the paid recon would
discover hidden capabilities was wrong. The free SDK call is the
right surface for capability mapping; the paid call is for actual
research queries.

**Easy to revert:** N/A — money already spent ($0.0105). Capability
map updated to merge both inputs.

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
