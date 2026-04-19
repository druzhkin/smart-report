# Night Upgrade — Output Layer v4 (2026-04-18 → 19)

**Goal:** превратить плоский markdown-отчёт в акционерный docx-продукт с таблицами, графиками, callouts, Q&A, cover page.

**Budget ceiling:** $20 total. Track A итерации на моках, один финальный full LLM-прогон в самом конце.

**Fixtures:** `runs/night_upgrade/fixtures/` (4 DR-отчёта, real input).

**Baseline commits (v4 branch):** 664b67a, 367b524, 3f31039, 41cd825 (frontend).

**Uncommitted at start:** design reskin (frontend), prompts/prompt_master.md XML upgrade, reference/PROMPT_MASTER_LIBRARY.md. Not in scope for this night — tracks don't touch them.

---

## Live status (each track updates every ~45 min)

### Track A — Synthesizer Structured Output
Owner: agent-track-a  
Branch: `night/track-a`  
Started: 2026-04-18  
Last update: [00:00] Track A: started, reading spec + codebase, creating branch night/track-a
[00:45] Track A: COMPLETE — models extended (6 new classes + 7 fields on FinalReport), synthesizer.md rewritten with few-shots+12 anti-patterns, synthesizer.py coercers added, 34 new tests all pass, 119/119 total pass. Schema committed early for B/C.

### Track B — Professional DOCX Renderer
Owner: agent-track-b  
Branch: `night/track-b`  
Started: 2026-04-18  
Last update: [00:30] Track B: started, read spec + models.py. Track A schema committed (KeyNumberHighlight not KeyNumber for highlights — noted). Branch night/track-b created. Building docx_v4_consulting.py.

### Track C — Chart Generator
Owner: agent-track-c  
Branch: `night/track-c`  
Started: 2026-04-18  
Last update: [10:45] Track C: DONE. chart_renderer.py implemented (6 types: bar/line/pie/stacked_bar/waterfall/scatter), 14/14 tests green, 85 legacy tests still green. PNGs at runs/night_upgrade/chart_samples/. Mock ChartSpec used (TODO: swap to smart_report.models.ChartSpec after Track A merge). rcParams fix: axes.grid.axis not grid.axis. Fonts: DejaVu Serif (available). All PNGs 68–98 KB.

---

## Coordination notes

- Track A defines shared schema (FinalReport new fields, ChartSpec protocol). B and C consume it.
- Track A stabilizes schema first (~30 min), then B/C can reference it.
- C can start immediately with ChartSpec from the spec (§4 Track A item 1) — agreed contract.
- Final merge: A → B → C integration. Then one prod run.

## Final prod run checklist

- [ ] Recreate session from fixtures: question from spec §3, 4 source_reports from runs/night_upgrade/fixtures/
- [ ] Run Intake → Analyzer → Synthesizer (new prompt) → save FinalReport JSON
- [ ] Render new docx: `docx_v4_consulting.py` → `final_report_consulting.docx`
- [ ] Render legacy for contrast: `docx_v4_legacy.py` → `final_report_legacy.docx`
- [ ] Headless LibreOffice convert to PDF, extract first 3 pages as PNG into `preview/`
- [ ] Fill `EVAL.md`
- [ ] Fill `HANDOFF_NIGHT.md`

## Stop triggers (per spec §8)

- Synthesizer fails structured output after 3-4 prompt iterations → stop, document schema gap
- docx won't validate → stop, document renderer alternative needed
- matplotlib unavailable → use svgwrite/cairosvg (matplotlib IS available, checked: 3.10.8)
- $20 exhausted before final run → document and stop

## Hard rules (per spec §7)

1. FinalReport backward-compatible (new fields optional only)
2. Iterate Synthesizer on cached Analyzer output, not full pipeline re-runs
3. Keep old DOCX exporter as `docx_v4_legacy.py`, new one as `docx_v4_consulting.py`
4. Log all LLM calls to `runs/night_upgrade/<ts>/llm_log.jsonl`
5. Don't skimp on Opus for Synthesizer
6. Commit prefixes: `feat(v4):`, `refactor(v4):`
