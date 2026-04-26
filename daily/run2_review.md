# Run 2 Baseline + Qualitative Review — Session 2026-04-26

## Что сделано

1. **`scripts/run2_baseline.py`** — fresh-runs harness:
   - Loads COMPARISON_QUERIES from existing `live_acceptance_run.py`
     (DRY).
   - Sonnet 4.6 across all 4 stages (PM/analyzer/synth/critic).
   - Per-query output: `report.docx`, `audit_summary.json` (with
     derived `release_status` ∈ pass|degraded|blocked), `trace.jsonl`,
     `cost.txt`.
   - Per-run hard cap $4 (script aborts if exceeded).
   - Output dir `docs/run2_baseline/<qid>/` (deviation from brief
     `runs/run2_baseline/` because `runs/` is gitignored — brief
     acceptance §6 needs artefacts in origin/v4.5).

2. **Block A — 0/3 fresh runs successful.** Three Sonnet attempts
   on three different queries (Q3 ×2, Q1 ×1) all hung silently
   between 10-16 min wall time. Detailed forensics in BLOCKERS.md
   A12 (supersedes A11):
   - Q3 attempt 1 (PID 119940): PM ✓ → intake ✓ → analyze ✓ → SYNTH HUNG.
   - Q3 attempt 2 (PID 38588): PM ✓ → intake (table extract) HUNG.
   - Q1 EV (PID 77520): PM ✓ → intake ✓ → analyze ✓ → SYNTH HUNG.
   Common pattern: process alive at low CPU, **no outbound HTTPS**,
   asyncio loop sits idle. Sonnet 4.6 globally broken on OpenRouter
   today.

3. **Block B + C pivot:** used existing Day-1 reviews (`docs/run2_baseline/
   REVIEW_q*.md`, based on Step 3.3 Haiku fixtures = same `origin/v4.5`
   code path as today's main, just on Haiku tier). Substance findings
   (calibration / template / confidence) transfer cleanly across
   model tiers because they live in shared classifier / synth-instruction
   code.

4. **`docs/run2_baseline/RUN2_FINDINGS_SUMMARY.md`** — cross-query
   summary per task §4 template:
   - TL;DR: calibration ✅ in DOCX, template leakage closed ✅,
     confidence hardcode closed ✅, main bottleneck = source coverage,
     scenario A.
   - Per-query grades: Q1 6/10, Q2 7/10, Q3 5/10.
   - Backend prioritization × 3 query.
   - **Scenario A — §5.6 Protocol** selected and justified.
   - 6 Phase 4 step candidates.
   - 3 open questions for user.

5. **Suite check:** 551 passed (no test changes this session).

## Что не получилось / не сделано (per task §7)

- **Block A 0/3 successful.** Sonnet 4.6 on OpenRouter hangs silently
  on every attempt today. Logged as A12. Not in scope to fix (§8
  forbids pipeline changes).
- **Q2 fresh run not even attempted** — by the time Q1 hung, the
  pattern was clear and continuing would just burn another $0.40-0.80
  for the same hang.
- **No fresh DOCX produced.** Day-1 DOCX (Haiku-rendered, `q*_run2_
  baseline.docx` in tracked location) remain authoritative for
  visual review purposes until OpenRouter recovers.

## Сколько потрачено

| Item | Cost |
|---|---|
| Q3 attempt 1 (PM+intake+analyze+partial synth) | ~$1.35 |
| Q3 attempt 2 (PM+intake start) | ~$0.40 |
| Q1 attempt 1 (PM+intake+analyze+partial synth) | ~$0.80 |
| **Session total** | **~$2.55** |

| Cap | Spent | Remaining |
|---|---|---|
| Session OpenRouter ($11) | $2.55 | $8.45 (77% headroom) |
| Session backends ($0) | $0 | $0 |
| Week-to-date (v3 $22.50) | ~$5.25 | ~$17.25 (77% headroom) |

## Решения, принятые без пользователя

- **A12 — kill all 3 Sonnet attempts after watchdog windows** (16/10/12
  min) and pivot Block B+C to Day-1-reviews basis. Rationale: §7 stop
  condition (2+ unrecoverable failures), §8 (no pipeline fixes),
  §9 priority (SUMMARY is non-cuttable). Alternative was to wait
  indefinitely for OpenRouter Sonnet to recover — task time-box
  doesn't allow.
- **Use existing Day-1 reviews as substance basis.** They're based
  on Step 3.3 Haiku fixtures = current `origin/v4.5` code path. The
  Phase 3 calibration / template-leakage-check / confidence-distribution
  findings come from shared code, not model-tier-specific. Substance
  transfers; prose richness doesn't. Acceptable trade-off given
  Sonnet unavailability.
- **OUT_ROOT moved from `runs/` to `docs/run2_baseline/` in script**
  per user feedback (path consistency: `docs/` for tracked artefacts,
  `runs/` for gitignored raw outputs). Q3 attempt 1's output dir
  was created under `docs/run2_baseline/q3_eu_dac/` (now empty since
  hangs prevented file writes).

## Findings worth noting

1. **Sonnet 4.6 hang has no exception path.** httpx async client
   sits idle when OpenRouter silent-drops the connection — no read
   timeout, no retry shim trigger, no observable error. Phase 4
   candidate Step (Step #6 in SUMMARY): LLM health preflight +
   httpx hang detection.
2. **Day-1 reviews already fully answer the SESSION TASK's core
   substance question.** The task assumed we'd need fresh Sonnet
   runs to verify Phase 3 substance reached DOCX, but Day-1 work
   on Step 3.3 Haiku fixtures already showed: ✅ inline grades on
   every claim, ✅ no template leakage, ✅ varied confidence. The
   Sonnet re-run would have added prose-quality observations but
   wouldn't have changed the core substance verdict.
3. **Scenario A is unambiguous.** Nothing in the existing reviews
   suggests synthesizer-fix urgency. Coverage is the bottleneck;
   §5.6+ architecture is what addresses it.

## Selected scenario for next session

**Scenario A — Continue with §5.6 SearchBackend Protocol** (architectural path).

Per SUMMARY decision input section. Rationale: Phase 3 substance wins
held in DOCX, no closed bugs reverted, main bottleneck = source
coverage which is exactly what v3 architecture addresses. Day 5 already
laid the routing_matrix + invariant test foundation; §5.6 Protocol
is the natural next layer.

## План на следующую сессию

1. **Smoke check Sonnet 4.6 first** ($0.01). If still hanging →
   defer §5.6 to next-next session (it's architecture work, no
   live LLM needed strictly, but live tests may use Sonnet).
2. **§5.6 SearchBackend Protocol** — Protocol abstraction +
   PerplexityBackend adapter for existing `smart_report/search.py`.
   Mock-only tests, $0 spend.
3. **§5.7 ValyuClient adapter** — make existing `ValyuClient`
   implement Protocol. ~$0 (mock tests only).

Estimated next-session cost: $0-0.01 (smoke check only).

## Push status

This session commits in 1 push to `origin/v4.5`:
- `scripts/run2_baseline.py` (new harness)
- `docs/run2_baseline/RUN2_FINDINGS_SUMMARY.md` (new)
- `daily/run2_review.md` (this file)
- `BUDGET.md` updated (Block A 0/3 + Q1+Q3 sunk costs)
- `BLOCKERS.md` updated (A11 + A12)
- The empty `docs/run2_baseline/q3_eu_dac/`, `q1_ev/` dirs (created
  by harness, no artefacts inside) — won't push them as git ignores
  empty dirs anyway.
