# Milestone 1 verdict request — RETRY (after Q1 EV FAIL)

## Context

First M1 attempt used Q1 EV (Russian automotive market). Opus correctly
verdict'ed FAIL on criterion 1 — Q1 EV is structurally a `russian_market`
question and synthesizer correctly ignored Tesla SEC filings as
irrelevant. The pipeline worked; the test query was wrong.

This retry uses an in-domain financial_us query (Tesla/Rivian/Lucid
SEC + FRED + BLS) so the brief's load-bearing criterion 1 (≥3 citations
from {sec.gov, federalreserve.gov, bls.gov, fred.stlouisfed.org}) can
actually be exercised. **No uploaded markdowns** — Valyu IS the only
source pool, so any DOCX citations come exclusively from the
SearchBackend Protocol → ValyuAdapter → pre_analyze_augment chain.

## Pre-flight pass on the new artefacts

Pre-Opus grep verdict:
- sec.gov: **3** ✅
- fred.stlouisfed.org: **2** ✅
- bls.gov: **1** ✅
- Total financial_us domain hits: **6** ≥ 3 → criterion 1 PASS
- Inline grade tags: STRONG 0 / MODERATE 0 / WEAK 16 / SPECULATIVE 9
  → 2 distinct grades only, fails criterion 4 (need ≥3 distinct).
  Note: 0 STRONG/MODERATE because source-quality classifier
  (Step 3.3 self-assessed) graded all the auto-blog/news domains
  honestly as WEAK and the projection statements as SPECULATIVE.
  This is the classifier doing its job, not a bug.
- evidence_quality: LOW_EVIDENCE_QUALITY (Step 1.2 source-adequacy
  detector — only 12 sources, no STRONG, fails the bar).

## Artefacts to check

- `docs/run2_baseline/q_fin_tesla_us/report.docx`
- `docs/run2_baseline/q_fin_tesla_us/audit_summary.json` (includes
  `valyu_augment` block: augment_fired=true, source_count=10, cost $0.015)
- `docs/run2_baseline/q_fin_tesla_us/trace.jsonl`

## Numeric acceptance criteria (same as first attempt)

1. **≥3 citations with domain in `{sec.gov, federalreserve.gov,
   bls.gov, fred.stlouisfed.org, edgar.sec.gov}`.**
   Pre-flight count: 6.

2. **Visible quality_tier marking on claims.**
   Inline `[STRONG]/[MODERATE]/[WEAK]/[SPECULATIVE]` prefixes appear
   in main_synthesis. Pre-flight count: 25 total (16 WEAK + 9 SPECULATIVE,
   distinct categories: 2).

3. **Template leakage regex: 0 hits.**
   No f-string placeholders in DOCX text.

4. **Confidence values vary (≥3 distinct).**
   Pre-flight: only 2 distinct grades fired (WEAK, SPECULATIVE).
   No STRONG/MODERATE because source-quality classifier honestly
   graded the available sources at WEAK (auto news, vendor blogs,
   IR materials) and synthesizer projections as SPECULATIVE.
   This is brief criterion 4 NOT met. Worth weighing whether a
   2-distinct-grade output on a Valyu-only run is genuine signal
   ("classifier is honest about thin source pool") or a failure
   mode ("Valyu sources should have surfaced ≥1 STRONG").

5. **Substance grade you assign ≥6/10.**
   Read the DOCX as a research analyst.

6. **New Valyu citations vs Run 2 baseline.**
   Run 2 baseline DOCX (Q1 EV Step 3.3 fixture) had ZERO citations
   from sec.gov/fred/bls. This run has 6. Net new: 6 — clear PASS.

## Question for Opus

For each of the 6 criteria, met yes/no with evidence.

Substance grade. Missing-source list. Verdict (PASS / PARTIAL / FAIL)
+ rationale. If FAIL/PARTIAL — what to fix.

**Special note on criterion 4:** the brief's "≥3 distinct grades" was
written for queries with mixed source quality (some primary regulators
→ STRONG, some media → MODERATE, some blogs → WEAK). On a Valyu-only
financial_us query, the available source pool is Tesla IR / news / SEC
filings — none of which the source-quality classifier promotes to
STRONG (SEC filings should arguably be primary_regulator → STRONG,
but the current classifier registry maps `sec.gov` to vendor-blog by
default). This is a Phase 4 candidate (Step 1 in PHASE_4_PRIORITIZATION:
DOCX reliability rendering) — not an M1 blocker.
