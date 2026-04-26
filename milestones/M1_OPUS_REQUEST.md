# Milestone 1 verdict request

## Context

Two-week brief Milestone 1 (days 1-3): **Valyu in production on financial_us domain.**
Goal: a Q1 EV DOCX where SEC/FRED citations are sourced from real Valyu calls
(not Perplexity-only baseline). Substance proof of the first new backend
landed in production.

Architectural foundation (already shipped, do NOT re-evaluate):
- §5.6 SearchBackend Protocol (commit 9b80197)
- ValyuAdapter implementing the Protocol (commit 2fecfa2)
- Pre-analyze augment module gated by `SMART_REPORT_VALYU_ENABLE_DOMAINS`
  env var (commit 57219b6 + this session's harness wiring)
- Harness DOCX checkpoint after first synth, closing A14 (commit 2fecfa2)

Production run executed today (2026-04-26):
- Query: Q1 EV (Russian electric vehicle market)
- Env: `SMART_REPORT_VALYU_ENABLE_DOMAINS=financial_us`
       `SMART_REPORT_VALYU_FORCE_DOMAIN=financial_us`
- Domain forced to financial_us so Valyu fires regardless of question-text
  heuristic detection (Q1 EV would normally classify as ru_automotive →
  russian_market and skip Valyu per Day 5 capability map).
- Models: Sonnet 4.6 across all stages (PM/analyzer/synth/critic).

## Artefacts to check

- `docs/run2_baseline/q1_ev/report.docx` (text-extracted in attached
  payload below)
- `docs/run2_baseline/q1_ev/audit_summary.json` (attached, includes
  `valyu_augment` block with augment_fired/source_count/cost)
- `docs/run2_baseline/q1_ev/trace.jsonl` (head 200 events attached)

## Numeric acceptance criteria

1. **≥3 citations with domain in `{sec.gov, federalreserve.gov, bls.gov,
   fred.stlouisfed.org, edgar.sec.gov}`** or equivalent Valyu proprietary
   financial corpora. Count occurrences of these domains in the DOCX text.

2. **Visible quality_tier marking on claims.** Inline grade prefixes
   `[STRONG]` / `[MODERATE]` / `[WEAK]` / `[SPECULATIVE]` should appear
   in the main_synthesis text. Count distinct grade tags used.

3. **Template leakage regex: 0 hits.** Search the DOCX text for
   f-string-style placeholders matching:
   `\{[a-z_]+\}`, `\{\{[^}]+\}\}`, `\$\{[^}]+\}`,
   or the specific Run 1 finding 5 marker:
   `On '[^']+', the merged engine output points to`. Report 0/non-0.

4. **Confidence values vary (≥3 distinct).** From the audit_summary
   `evidence_grade_distribution` count how many of STRONG/MODERATE/
   WEAK/SPECULATIVE have non-zero counts. Acceptance: ≥3 distinct
   non-zero categories (i.e., not just "all STRONG").

5. **Substance grade you assign ≥6/10.** Read the DOCX as a research
   analyst. Does it answer the question with traceable, well-cited,
   honest claims? Score 1-10.

6. **New Valyu citations vs Run 2 baseline.** Earlier Run 2 baseline
   (Day-1 Step 3.3 Haiku fixtures, no Valyu) produced a Q1 EV report
   with 18 sources, NONE from sec.gov / fred / bls. This run should
   show new citations from those domains that the baseline did not
   have. List them.

## Question for Opus

For each of the 6 criteria above:
1. Met yes/no, with one-line evidence (citation, exact quote, count).
2. Substance grade DOCX (1-10) per criterion 5.
3. Missing sources you'd expect that don't appear (e.g. specific 10-K
   filings, FRED series).
4. Verdict: **PASS / PARTIAL / FAIL** + 3-5 line rationale.
5. If FAIL/PARTIAL — what to fix before Milestone 2.

Strict rule: PASS only if criteria 1-4 ALL met. PARTIAL if some met.
FAIL if criterion 1 (≥3 sec.gov/fred citations) is missed — that's the
load-bearing one for "Valyu in production" claim.
