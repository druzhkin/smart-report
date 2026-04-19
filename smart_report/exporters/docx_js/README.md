# DOCX v2 Renderer — Node.js + docx-js

Navy/gold consulting report renderer. Supersedes python-docx Track B for visual quality.

## Setup

```bash
cd smart_report/exporters/docx_js
npm install
```

Requires Node.js v22+.

## CLI Usage

```bash
node main.js <input.json> <output.docx> [--chart-dir <path>]
```

- `input.json` — FinalReport serialized to JSON (see `smart_report/models.py::FinalReport`)
- `output.docx` — output path
- `--chart-dir` — optional directory with pre-rendered PNGs: `chart_00.png`, `chart_01.png`, ...

## Python Integration

```python
from smart_report.exporters.docx_js_bridge import render_docx_js
from pathlib import Path

output_path = render_docx_js(
    final=final_report,
    output_path=Path("report.docx"),
    chart_dir=Path("charts/"),
)
```

## Data Contract (FinalReport JSON fields consumed)

| Field | Usage |
|-------|-------|
| `question` | Cover title, header |
| `session_id` | Cover footnote |
| `executive_summary.main_answer` | ES intro paragraph |
| `executive_summary.top_findings` | ES numbered list |
| `executive_summary.confidence_note` | Gold callout |
| `executive_summary.what_meta_adds` | Gold callout |
| `key_numbers_highlight[]` | KPI 48pt grid (value/label/source_ref) |
| `qa_section[]` | Q&A В:/О: blocks |
| `ranking[]` | Prioritization table |
| `main_synthesis` | Markdown → parsed chapters |
| `tables[]` | Structured data tables |
| `charts[]` | Chart specs (PNGs from chart_dir) |
| `callouts[]` | Insight/warning blocks |
| `consensus_section` | Consensus markdown |
| `conflicts_section` | Conflicts markdown |
| `gaps_filled_section` | Gaps markdown |
| `all_sources[]` | Numbered bibliography |

## Citation system [N]

The synthesizer emits `[N]` markers inline in `main_synthesis` text. The renderer
faithfully preserves them in paragraph text — no pre-pass substitution needed.
Sources are numbered in order of appearance in `all_sources[]`, grouped by `tool`.

## File structure

```
part1_core.js      — Palette C{}, primitives P/R/H1/H2/H3/caption/spacer/hr,
                     callout, kpiCard, kpiRow, dataTable, bullet, numbered,
                     embedImage, parseMarkdownBlocks
part2_sections.js  — buildCoverPage, buildExecutiveSummary, buildTableOfContents,
                     buildMainChapters, buildSourcesSection, extractTocItems
main.js            — CLI entry point, Document assembly with 2 Sections,
                     numbering config, styles, header/footer
```

## Design tokens (palette)

```js
primary:     "#1F3A5F"   // deep navy — headings, accents
accent:      "#C9A961"   // gold/brass — premium accent
accentSoft:  "#F0E4C4"
bgCallout:   "#EEF2F7"
bgTable:     "#F7F4ED"
success:     "#2E7D4F"
danger:      "#A0321C"
```

Font: Calibri. Sizes in half-points: 22 = 11pt, 96 = 48pt (KPI cards).

## Hard constraints (methodology §10)

1. `ShadingType.CLEAR` with `fill` + `color: "auto"` — never SOLID
2. Column widths in DXA, never PERCENTAGE (US Letter: 9360 DXA content width)
3. Bullets/numbered via `numbering.config`, never unicode `•`
4. `PageBreak` only inside `new Paragraph({ children: [new TextRun({ break: 1 })] })`
5. Russian quotes `«»` `„"`, not `""`
6. Duplicate `columnWidths` at Table level AND `width` on each cell
