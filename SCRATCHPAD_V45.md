# v4.5 Semantic Layer — Live Status (each track updates every ~30 min)

**Goal:** закрыть 4 провала v4 ночного — потерю источников (80% → <20%), потерю фактов (70% → <25%), внутренние противоречия, английские термины.

**Fixtures:** `runs/night_upgrade/fixtures/` (4 DR-отчёта).
**Cached:** `runs/night_upgrade/cache_analysis.json` (AnalysisOutput), `cache_final.json` (текущий плохой FinalReport для сравнения).
**Budget ceiling:** $25. Tracks iterate on cached Analyzer output; one final prod run.

---

### Track 1+4 — Schema & Data Pipeline (citations + fact preservation, MERGED)
Owner: agent-schema-pipeline
Branch: `schema-pipeline` (git ref constraint prevented `v4.5/schema-pipeline`)
Started: 2026-04-18
Last update: 2026-04-18

**Status: COMPLETE (no LLM calls — schema + code + tests done)**

#### Delivered
- `smart_report/models.py` — added SourceRef, Claim, NumericFact, QualitativeFact, CitedText, NumberedSource, NormalizedReport; extended AnalysisOutput (all_numeric_facts, high_relevance_facts, fact_coverage_target); extended FinalReport (bibliography, citation_coverage, source_count); V4Session.normalized_reports
- `smart_report/intake.py` — regex citation extraction (4 formats: [[N]](url), citeturn, [N]+bib, [text](url)); LLM fact extraction via Opus; normalize_report() / normalize_all_reports()
- `prompts/intake.md` — Opus prompt with anti-patterns: НЕ АГРЕГИРУЙ, target 200-1000 facts per 500 lines
- `smart_report/analyzer.py` — added normalized_reports param; _aggregate_facts() deduplicates by fact_id, computes high_relevance_facts (relevance in high/medium) and fact_coverage_target = len(high_relevance) * 0.85
- `prompts/synthesizer.md` — added ПРАВИЛО CITATION + ПРАВИЛО DATA PRESERVATION sections; anti-patterns 0 and 0b added
- `smart_report/synthesizer.py` — _build_facts_section() injects high_relevance_facts + fact_coverage_target into Synthesizer context (up to 200 facts)
- `smart_report/bibliography.py` — generate_bibliography(): scans [REF:url] → [N], builds NumberedSource list, computes citation_coverage
- `smart_report/data_audit.py` — audit_fact_coverage(): fact presence detection in all text fields; CoverageReport with verdict excellent/acceptable/poor/critical_failure; build_retry_feedback()
- `smart_report/v4_orchestrator.py` — synthesize() now runs bibliography + audit post-processing; one retry if verdict poor/critical_failure; CoverageReport saved to metadata
- `smart_report/exporters/docx_v4_consulting.py` — [N] rendered as superscript; _render_bibliography() with grouping; _render_appendix_missing_facts() for poor-verdict appendix

#### Tests
- `tests/test_intake_citations.py` — 15 tests (4 citation formats, accessed_via, mocked LLM)
- `tests/test_bibliography.py` — 10 tests (sequential numbering, coverage metric, edge cases)
- `tests/test_data_audit.py` — 13 tests (verdict thresholds, retry feedback, multi-field detection)
- `tests/test_synthesizer_citations.py` — 7 tests (REF→[N] pipeline, orchestrator post-processing, deterministic IDs)

**Test delta: 194 → 217 passing (23 new, 3 expensive/fixture-skipped)**

#### Blockers/Notes
- No LLM calls made (schema+infra track only; prompt tuning against cached data is next step)
- `AnalysisOutput` uses `extra="forbid"` via `_V4Base` — new fields added with defaults, backward-compat OK
- `NormalizedReport` and new citation models use `extra="ignore"` (more tolerant for LLM output)
- `FinalReport` backward-compatible: bibliography=[] and citation_coverage=0 by default

### Track 2 — Consistency Critic
Owner: agent-consistency
Branch: `v4.5/consistency`
Started: — (stages after schema from Track 1+4 is ~stable)
Last update: —

### Track 3 — Language Lint
Owner: agent-language
Branch: `v4.5/language`
Started: —
Last update: —

---

## Coordination notes

- Track 1+4 defines canonical schema expansion (SourceRef, Claim, NumericFact, QualitativeFact, CitedText, FinalReport additions). Tracks 2 and 3 read from the spec text directly for contract; they rebase on Track 1+4 merge commit at the end.
- Track 2 (Critic) can run before Track 1+4 schemas land by working on the CURRENT FinalReport schema as input — it only needs to detect internal inconsistencies in final_report.json text. Schema expansion from Track 1+4 is additive so integration is clean.
- Track 3 (Language) is 100% independent — just a post-processing lint + Synthesizer prompt directive. No schema deps.

## Final prod run checklist

- [ ] Merge Track 1+4, Track 2, Track 3 into `v4.5`
- [ ] Restart backend on v4.5
- [ ] Reuse cached Analyzer output if schemas are backward-compat, or re-run Intake+Analyzer if they need fact extraction
- [ ] Synthesize + Critic loop (max 1 retry) on cached/fresh analyzer output
- [ ] Run post-processing: bibliography, coverage audit, language lint
- [ ] Render `after.docx` via docx_v4_consulting (or docx_js)
- [ ] Copy `night_upgrade/20260419T075849Z/final_report_consulting.docx` → `before.docx`
- [ ] Measure: source_count, citation_coverage, numeric_facts_retention, language_warnings, consistency_issues
- [ ] EVAL.md + HANDOFF_V45.md

## Hard rules (spec §7)

1. FinalReport backward-compatible at render level
2. Source preservation > text aesthetics
3. Critic retry limited to 1
4. No full pipeline on each iteration — use cached
5. LLM calls logged to `runs/v4_5/<ts>/llm_log.jsonl`
6. Old tests stay green (193 now)
7. One branch per track, merge at end
8. Not pushed

## Target metrics

| Metric | Current (v4 night) | Target (v4.5) |
|---|---|---|
| Source count | 20 | 80+ |
| Citation coverage (numeric) | ~0% | >85% |
| Numeric fact retention | ~30% | >75% |
| Language warnings | ~30 | <5 |
| Critical consistency issues | 3 | 0 |
