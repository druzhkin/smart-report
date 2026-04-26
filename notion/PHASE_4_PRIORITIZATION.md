# Phase 4 — Candidate Step Prioritization

**Source:** `docs/run2_baseline/RUN2_FINDINGS_SUMMARY.md` (6 candidates), updated with `BLOCKERS.md` A13 root cause from Sonnet unblock session.

**Decision basis:** Substance verdict from Run 2 review (Day-1 Haiku fixtures + pending Sonnet baseline verification) + Day 5 Valyu coverage map + v3 brief routing invariant constraints + A13 finding that pipeline synth is slow-but-working on Sonnet.

**Authoring note:** This is **prep for Phase 4 brief**, not the brief itself. Phase 4 brief is Day 6 v3 after the full A/B run. Here we rank candidates so future sessions don't get stuck on "what to build next?" once §5.6+ Protocol architecture lands.

---

## Prioritization framework

Each Step scored on:

- **Impact** (1-5): how much substance pain it removes on current Q1/Q2/Q3 query set
- **Cost** (1-5, 5 = cheap): LLM + dev time to implement (5 = pure code, 1 = multi-day backend integration)
- **Risk** (1-5, 5 = low risk): chance of breaking existing 551 tests or invariant
- **Synergy** (1-5): how much it enables follow-on work (Valyu integration, A/B run, future backends)
- **Score** = Impact + Cost + Risk + Synergy (max 20)

---

## Ranked list

### 1. RU regulatory backend (Rosstat / CBR / MOEX / EISJS) — Score 16/20

- **What:** Distinct backend module separate from Valyu/Tavily/Exa,
  wrapping Rosstat statistics API + CBR Statistics API + MOEX
  SmartLab API + EISJS for primary RU data. Routes via `routing_matrix`
  for `russian_market` domain as augment to Perplexity primary.
- **Why now:** Q2 Moscow RE review surfaced this as **the** missing
  piece — every RU number cited goes through RBC/Kommersant secondary,
  primary stats agencies are not reachable. Q1 EV partial: Минпромторг
  also absent. Without this, A/B Q2 will show config B ≡ config A
  (Valyu n/a, Tavily basic ≈ Perplexity), making the A/B Q2 row
  effectively a noise check.
- **Acceptance:**
  - 3 backend clients (Rosstat REST, CBR REST, MOEX SmartLab) with
    retry shim mirroring `ValyuClient`
  - `russian_market` route in orchestrator emits at least 1 source
    from these backends per Q2 query
  - 5 tests per backend (success / 4xx / 5xx retry / empty / live smoke)
- **Cost estimate:** 2-3 sessions of dev (~8-12 hours engineer time);
  $0-0.05 in API calls (Rosstat is free; CBR free; MOEX free)
- **Depends on:** §5.6 Protocol abstraction (so the new clients
  implement the same `SearchBackend` interface)
- **Enables:** Q2 Moscow RE A/B finally has actual delta to measure;
  Phase 4 brief can credibly claim Smart Report covers RU primary
  data
- **Score breakdown:** Impact 5 (closes biggest visible gap on Q2),
  Cost 3 (multi-session dev but free APIs), Risk 4 (new backends,
  isolated), Synergy 4 (proves Protocol works for non-Valyu, sets
  pattern for future regional backends)

### 2. DOCX render `all_sources[].reliability` with classification reason — Score 15/20

- **What:** Add a "Источники: уровень доверия и обоснование" section
  to the rendered DOCX showing each source's `reliability` (HIGH/
  MEDIUM/LOW from Step 3.3) plus the *reason* (which classifier rule
  fired: `primary_regulator` / `trusted_media` / `vendor_blog` /
  `forum_or_aggregator` / etc).
- **Why now:** Day-1 reviews of all 3 queries surfaced this: inline
  `[STRONG]/[MODERATE]/[WEAK]/[SPECULATIVE]` grades are visible on
  every claim, but the analyst can't see WHY a particular source
  was downgraded to MODERATE. The signal exists in `all_sources[].
  reliability` metadata; it's just not rendered. Adding it makes
  Phase 3 Step 3.3 work fully visible to the end user.
- **Acceptance:**
  - DOCX has a new section under "Источники" with one row per
    source: URL, title, reliability tier, classification rule that
    fired, brief 1-line "why" derived from the classifier
  - 3 unit tests on `docx_v4_consulting.py` and `docx_js` rendering
    (one per reliability tier)
  - Visual diff vs current DOCX shows new section, no other layout
    regressions
- **Cost estimate:** 1 session (~3-4 hours); $0 LLM
- **Depends on:** Nothing — Phase 3 already has the metadata; this
  is pure rendering.
- **Enables:** Aligns with v3 brief §3.4 degradation_warning rendering
  pattern (both show provenance to user); demonstrates the
  reliability mechanism for stakeholder review.
- **Score breakdown:** Impact 4 (visible per-claim "why" is high
  value for users), Cost 5 (pure code, no LLM), Risk 4 (rendering
  changes have visual but rarely test impact), Synergy 2 (independent;
  doesn't unlock other work directly)

### 3. Sonnet 4.6 health check + httpx hang detection (LLM observability) — Score 14/20

- **What:** Per A13: distinguish "actively streaming bytes" from
  "TCP idle" so harness watchdogs can cancel only true hangs, not
  slow legitimate generations. Plus session-level emitter event
  for "tokens received so far" so harness watchdogs use real
  progress, not wall-clock heuristics.
- **Why now:** Run 2 baseline session and Sonnet unblock session
  both burned ~$5 between them on watchdog-killed runs that were
  actually progressing. Without this signal, every future Sonnet
  Run-2-style session has the same risk. Cheap to implement, big
  operational win.
- **Acceptance:**
  - `smart_report.llm.call_json` emits a periodic "bytes received"
    event during long requests (every N bytes or every 10s)
  - Harness scripts (`scripts/run2_baseline.py`, future A/B harness)
    consume the event and reset their watchdog; only stale-progress
    triggers kill
  - 1 test demonstrating watchdog DOES NOT kill on legitimate slow
    generation; 1 test demonstrating it DOES kill on truly idle
    socket
- **Cost estimate:** 1 session (~4 hours); $0 LLM
- **Depends on:** Nothing.
- **Enables:** Future A/B + production runs — every Sonnet-tier
  run is at risk without this.
- **Score breakdown:** Impact 3 (operational, not user-facing),
  Cost 4 (~4 hours), Risk 4 (additive, low chance of breaking),
  Synergy 3 (every future Sonnet run benefits)

### 4. evidence_gaps in DOCX even when query goes through template path — Score 12/20

- **What:** Q2 RU RE goes through the strategic template
  decomposition path → `sub_questions` empty → gap_detector skipped
  → `evidence_gaps` array empty → DOCX has no "missing evidence"
  section. Architectural artefact of Step 2.1 design. Need a
  template-path-aware gap detection that runs on `final_report`
  level (post-synth) and surfaces explicit "X not found in any
  source" callouts.
- **Why now:** Q2 review specifically surfaced this — analyst sees
  no explicit "Росстат не цитируется" warning, has to infer it
  themselves. Reduces trust in the report's coverage signalling.
- **Acceptance:**
  - New `post_synth_gap_pass(final_report, query_domain)` function
    that flags missing authoritative sources for the domain
  - DOCX renders these as a "Открытые пробелы в источниках"
    callout block when present
  - 3 tests: one per QueryDomain (russian_market, eu_regulatory,
    general)
- **Cost estimate:** 1-2 sessions (~6 hours); $0 LLM (pure pipeline)
- **Depends on:** routing_matrix (Day 5 already done)
- **Enables:** Phase 4 brief can demonstrate gap-coverage signalling
  works on all query types, not just LLM-planner ones.
- **Score breakdown:** Impact 3 (Q2-specific now, but generalises),
  Cost 4 (one focused sprint), Risk 4 (new code, isolated),
  Synergy 1 (mostly self-contained)

### 5. Synthesizer: warn on untagged claim ratio > 15% — Score 11/20

- **What:** Q1 EV review noted ~21% claims without `[STRONG]/
  [MODERATE]/[WEAK]/[SPECULATIVE]` grade prefix. Either short
  connecting phrases (acceptable) or synthesizer skipped grading
  (bug). Add post-synth audit pass that counts untagged claims
  vs total, warns/retries if untagged > 15%.
- **Why now:** Step 3.3 promised every claim gets a grade. ~21% slip
  rate undermines the promise. Improvement opportunity surfaced by
  Day-1 Q1 review. Lower urgency than #1-3 because it's a polish
  item, not a missing capability.
- **Acceptance:**
  - Audit function in `smart_report/data_audit.py` returns
    untagged_ratio
  - If > 15%, synthesize retries with explicit "grade EVERY claim"
    feedback (mirrors language_lint retry pattern)
  - Test on a synthetic synth output where 25% claims are
    untagged → retry triggered; another with 5% → no retry
- **Cost estimate:** 1 session (~3 hours); ~$0.50 in test LLM
  calls
- **Depends on:** Nothing.
- **Enables:** Step 3.3 quality story is fully tight; Phase 4 brief
  can claim "100% claims graded" instead of "~80%".
- **Score breakdown:** Impact 2 (polish), Cost 4, Risk 4,
  Synergy 1

### 6. regulatory_eu degradation observability — Score 11/20

- **What:** Per Day 5 + A13: every `regulatory_eu` query will
  trigger v3 §3.4 degradation_warning (Valyu has no eur-lex). Need
  per-domain degradation rate telemetry so we know:
  (a) is the routing actually firing as expected,
  (b) is the warning rendering reliably,
  (c) does it correlate with worse evidence_quality outcomes.
- **Why now:** v3 routing matrix was built around assumed Valyu
  EU coverage that doesn't exist. The degradation pattern IS the
  design (visible to user), but we need to verify it's working.
  Without telemetry, Phase 4 brief makes claims about coverage
  gaps without evidence on rate of occurrence.
- **Acceptance:**
  - Per-run JSON includes `degradation_events: [{domain, primary,
    augment_used, reason}]`
  - Aggregate dashboard query (Markdown summary file, not real
    dashboard) computes degradation rate by domain across last
    N runs.
  - Tests on routing_matrix decisions: regulatory_eu correctly
    triggers degradation; financial_us does not (when SEC corpus
    works).
- **Cost estimate:** 1-2 sessions (~6 hours); $0-0.20 LLM
- **Depends on:** §5.6 Protocol + §5.13 Orchestrator with degradation
  routing actually wired (not just stub)
- **Enables:** Phase 4 brief writes credible coverage-gap section
  with numbers.
- **Score breakdown:** Impact 2 (observability not new capability),
  Cost 3, Risk 4, Synergy 2 (informs future Valyu coverage decisions)

---

## Recommended sequence

**Phase 4 sessions (in order):**

1. **§5.6 SearchBackend Protocol + Perplexity adapter** (current
   session if time, else next). $0. Foundation for all subsequent
   work.
2. **§5.7 Valyu adapter** (~$0). Proves Protocol works for
   primary-capable backend.
3. **#1 RU regulatory backend** (RU augment) — 2-3 sessions.
   Closes Q2 gap. Proves Protocol works for non-Valyu primary.
4. **§5.13 Orchestrator rewrite** with augment-on-failure semantics
   (~$0.50 testing). Activates the routing.
5. **#2 DOCX reliability rendering** — 1 session. Polish that
   makes the substance work visible.
6. **#3 LLM observability** — 1 session. Operational hygiene before
   the full A/B run.
7. **A/B run** (Day 5 v3 brief). $5-8. Real Phase-4-prep evidence.
8. **#4 evidence_gaps post-synth** — 1-2 sessions. Visible polish.
9. **#5 untagged claims audit** — 1 session. Step 3.3 closure.
10. **#6 regulatory_eu degradation observability** — 1 session.
    Phase 4 brief evidence.
11. **Phase 4 brief itself** — 1 session.

**Обоснование sequence (3-5 строк):** Protocol first (item 1) because
nothing else can ship cleanly without it. Items 2-4 build the Valyu-first
hybrid the v3 brief mandates. Item 3 (RU backend) is intentionally
inserted between 2 and 4 because A/B Q2 is meaningless without it.
Items 5-6 are operational/polish blocking the A/B run (item 7),
because without #3 the A/B will burn budget on watchdog-killed runs
again. Items 8-10 are post-A/B polish that make the Phase 4 brief
defensible. Brief itself is last.

---

## What's NOT in Phase 4 (deferred)

- **Tavily client (§5.9)** and **Exa client (§5.10)** — kept in
  v3 plan but moved to Phase 5 because (a) v3 brief explicitly
  marks them as augments, not core, and (b) Q1/Q2/Q3 review showed
  Valyu + RU regulatory backend close ~80% of substance gaps;
  Tavily/Exa are <20% incremental. Will revisit after A/B if
  evidence gaps remain.
- **technical_research outputSchema variant (v3 brief Variant D)** —
  exotic optimization, only needed if A/B reveals LLM synthesis
  cost dominates (currently it's PM+intake+analyze+synth roughly
  equal).
- **Cross-backend deduplication** — listed in Run 2 SUMMARY but
  not promoted to Phase 4 step because Day-1 reviews didn't show
  meaningful overlap problems with current single-Perplexity setup.
  Becomes relevant only after multiple backends are wired (post-§5.13).

---

## Provisional verdict caveat

The substance verdict driving this prioritization is currently from
**Day-1 reviews of Step 3.3 Haiku fixtures**. The Sonnet unblock
session (this one) verifies the same pipeline works on Sonnet
(Block B `runs/run2_sonnet_smoke/SONNET_VERIFY.md` if/when that
landed). If Sonnet substance verification reveals **different**
behaviour (e.g., calibration not visible, template leakage on
larger output), this prioritization needs revision and items
adjacent to synth (#5 untagged claims, possibly new Steps for any
Sonnet-specific issues) move up.
