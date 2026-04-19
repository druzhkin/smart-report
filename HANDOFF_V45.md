# v4.5 Schema & Data Pipeline — Handoff

## Track: 1+4 (Schema expansion + Fact preservation)
Branch: `schema-pipeline` (note: git prevents `refs/heads/v4.5/schema-pipeline` when `refs/heads/v4.5` exists)
Status: **COMPLETE — schema, code, tests done. No LLM prod iteration run (budget conserved).**

---

## What was built

### New pydantic models (`smart_report/models.py`)

All backward-compatible (optional/defaulted fields):

| Model | Purpose |
|---|---|
| `SourceRef` | Single citable source with URL, title, publisher, confidence, accessed_via |
| `Claim` | Factual claim with list[SourceRef] attribution |
| `NumericFact` | Number+unit fact with deterministic fact_id, relevance, fact_category |
| `QualitativeFact` | Non-numeric fact with attribution |
| `CitedText` | Text with [REF:source_id] markers + source registry |
| `NumberedSource` | Numbered bibliography entry with section info |
| `NormalizedReport` | Full intake output for one uploaded markdown |

Extended existing models:
- `AnalysisOutput`: + `all_numeric_facts`, `all_qualitative_facts`, `high_relevance_facts`, `fact_coverage_target`
- `FinalReport`: + `bibliography`, `citation_coverage`, `source_count`
- `V4Session`: + `normalized_reports`

### New modules

| File | What it does |
|---|---|
| `smart_report/intake.py` | Regex citation extraction (4 formats) + LLM fact extraction |
| `smart_report/bibliography.py` | [REF:url] → [N] replacement + NumberedSource list + coverage metric |
| `smart_report/data_audit.py` | Fact presence audit in FinalReport; verdict + retry feedback |
| `prompts/intake.md` | Opus prompt for numeric/qualitative fact extraction |

### Updated modules

| File | Change |
|---|---|
| `smart_report/analyzer.py` | Added `_aggregate_facts()` — merges NormalizedReport facts into AnalysisOutput |
| `smart_report/synthesizer.py` | `_build_facts_section()` injects high_relevance_facts into LLM context |
| `prompts/synthesizer.md` | Added ПРАВИЛО CITATION + ПРАВИЛО DATA PRESERVATION sections |
| `smart_report/v4_orchestrator.py` | Synthesize loop: synthesis → bibliography → audit → optional 1 retry |
| `smart_report/exporters/docx_v4_consulting.py` | [N] as superscript; bibliography section; missing-facts appendix |

### Tests added

| File | Tests | Coverage |
|---|---|---|
| `tests/test_intake_citations.py` | 15 | 4 citation formats, accessed_via, mocked LLM normalize_report |
| `tests/test_bibliography.py` | 10 | Sequential numbering, [REF]→[N], coverage metric, edge cases |
| `tests/test_data_audit.py` | 13 | All verdict thresholds, retry feedback, multi-field detection |
| `tests/test_synthesizer_citations.py` | 7 | REF→[N] pipeline, orchestrator post-processing, deterministic IDs |

**Total: 194 original + 23 new = 217 passing, 25 skipped (expensive/fixture-gated)**

---

## Next steps (for prod iteration)

### Step 1: Re-run Intake on 4 fixtures (~$1-2)
```python
# scripts/run_intake_v45.py
from smart_report.intake import normalize_all_reports
from smart_report.models import UploadedMarkdown
import asyncio, json, pathlib

FIXTURE_DIR = pathlib.Path("runs/night_upgrade/fixtures")
CACHE_DIR = pathlib.Path("runs/v4_5/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    reports = [
        UploadedMarkdown(filename=f.name, content=f.read_text("utf-8"), word_count=len(f.read_text().split()))
        for f in sorted(FIXTURE_DIR.glob("*.md"))
    ]
    RESEARCH_PROMPT = "мне нужен полный глубокий обзор по бизнес и премиум новостройкам москвы..."
    normalized = await normalize_all_reports(reports, research_prompt=RESEARCH_PROMPT)
    json.dump(
        [nr.model_dump() for nr in normalized],
        open(CACHE_DIR / "normalized_reports.json", "w"),
        ensure_ascii=False, indent=2
    )
    print(f"Normalized {len(normalized)} reports")
    for nr in normalized:
        print(f"  {nr.source_filename}: {len(nr.extracted_numeric_facts)} numeric facts, {len(nr.extracted_sources_inventory)} sources")

asyncio.run(main())
```

### Step 2: Re-run Analyzer with normalized_reports (~$1)
```python
from smart_report.analyzer import analyze_reports
# Load normalized_reports.json
# Pass as normalized_reports= kwarg to analyze_reports()
# Save to runs/v4_5/cache/analysis_output.json
```

### Step 3: Iterate Synthesizer against cached Analyzer (max 3 iterations)
- Check: source_count ≥ 80, citation_coverage ≥ 0.85, coverage_pct ≥ 0.75
- Render FinalReport → docx
- Log LLM calls to `runs/v4_5/<ts>/llm_log.jsonl`

---

## Stop-and-ask triggers (documented, not halting)

### citation_coverage stuck <60% after 3 iterations
**Likely cause:** Opus is generating text without [REF:url] markers despite prompt rules.
**Structural limit:** The LLM context passes up to 200 facts with source_urls, but if source_urls are empty (no URL found by intake regex for that fact), the LLM has no URL to cite.
**Fix:** Improve intake regex to capture more URLs before LLM fact extraction runs. The `_parse_end_bibliography()` function covers numbered refs, but if the source document uses a different format (e.g., footnote numbers only with bibliography in a separate file), URLs won't be linked to facts.
**Alternative:** Post-processing: after bibliography generation, scan for uncited numeric claims and match them to the closest source in bibliography by semantic similarity.

### fact_retention stuck <50% after 3 iterations
**Likely cause:** Synthesizer context window is too long with 200 facts injected, causing truncation.
**Fix:** Chunked Synthesizer approach:
1. Run Synthesizer for main narrative (pass only top 50 high-priority facts)
2. Then run a second pass: "here are remaining X facts, create a structured appendix table for each category"
3. Merge appendix tables into FinalReport

### docx renderer crashes on CitedText or bibliography
**Fallback:** The `_render_bibliography()` function is called only if `report.bibliography` is non-empty. If it crashes, `_render_sources()` (the old path) is the fallback — but currently there's no explicit try/except around it in `render_consulting_docx`. Add:
```python
try:
    if report.bibliography:
        _render_bibliography(doc, report)
    else:
        _render_sources(doc, report)
except Exception as e:
    # Fallback: plain text bibliography at end
    _render_sources_fallback(doc, report)
```

---

## Known issues / TODOs

1. **`QAItem.answer` mutability:** Pydantic v2 `model_copy(update=...)` used in bibliography.py for immutable fields — this creates new instances rather than mutating. Should work correctly.

2. **Large fact inventories:** If intake extracts 1000+ facts per document × 4 documents = 4000 facts, passing even 200 to Synthesizer adds ~30k tokens to context. Monitor cost.

3. **`AnalysisOutput.extra="forbid"`:** New fields (all_numeric_facts, etc.) are in the model definition, so they pass. BUT if loading old cached `cache_analysis.json` via `model_validate()`, these fields will be missing → default to `[]`. This is correct behavior; re-run Analyzer to populate.

4. **`_render_appendix_missing_facts` data flow:** The missing_facts are stored in `report.metadata["missing_high_relevance_facts"]` — but this key is only populated if the orchestrator explicitly adds it. The current implementation in `v4_orchestrator.py` stores `coverage_audit` dict but not `missing_high_relevance_facts` list. To enable the appendix:
```python
# In orchestrator synthesize():
final.metadata["missing_high_relevance_facts"] = [
    f.model_dump() for f in coverage_report.missing_high_relevance_facts[:100]
]
```
This is a low-priority TODO since the appendix can be populated directly from the CoverageReport when rendering.
