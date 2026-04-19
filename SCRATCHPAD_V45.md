# v4.5 Semantic Layer — Live Status (each track updates every ~30 min)

**Goal:** закрыть 4 провала v4 ночного — потерю источников (80% → <20%), потерю фактов (70% → <25%), внутренние противоречия, английские термины.

**Fixtures:** `runs/night_upgrade/fixtures/` (4 DR-отчёта).
**Cached:** `runs/night_upgrade/cache_analysis.json` (AnalysisOutput), `cache_final.json` (текущий плохой FinalReport для сравнения).
**Budget ceiling:** $25. Tracks iterate on cached Analyzer output; one final prod run.

---

### Track 1+4 — Schema & Data Pipeline (citations + fact preservation, MERGED)
Owner: agent-schema-pipeline
Branch: `v4.5/schema-pipeline`
Started: —
Last update: —

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
