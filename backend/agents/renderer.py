from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from langsmith import traceable
from loguru import logger


class RendererError(Exception):
    pass

from backend.config import settings
from backend.pipeline.model_router import AgentTask, estimate_cost, get_model
from backend.pipeline.state import AgentState
from backend.schemas.report_schema import ReportOutput, ReportSection
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry

SYSTEM_PROMPT = """You are a McKinsey-grade report writer using data from professional research.
Generate a comprehensive structured report with title, executive_summary, and sections array.
Each section has: title, content (full markdown with data, analysis, citations), order, sources (list of URLs).

Requirements:
- Executive summary: 300-400 words, actionable insights, key metrics with specific numbers.
- Generate AT LEAST 6-8 detailed sections covering all major aspects of the topic.
- Each section: minimum 400 words, thorough analysis with specific data points, statistics, and trends.
- TABLES: Always add a blank line before and after markdown tables. Format:

  Some text here.

  | Column 1 | Column 2 | Column 3 |
  |----------|----------|----------|
  | Value 1  | Value 2  | Value 3  |

  Continue text after table.

- Use markdown formatting: bold **key metrics**, bullet lists, tables for comparisons.
- Cite sources inline as [Source](url).
- Professional, authoritative tone. No filler. Dense with data.

Return valid JSON:
{
  "title": "...",
  "executive_summary": "...",
  "sections": [
    {"title": "...", "content": "...", "order": 1, "sources": ["url1", "url2"]}
  ]
}"""


@llm_retry()
async def _call_llm(system: str, user: str, model: str) -> str:
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": 32768,
    }
    if supports_json_mode(model):
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _ensure_table_spacing(text: str) -> str:
    """Ensure blank lines before/after markdown tables so python-markdown renders them."""
    import re
    # Add blank line before table rows if missing
    text = re.sub(r'([^\n])\n(\|)', r'\1\n\n\2', text)
    # Add blank line after table block if missing
    text = re.sub(r'(\|[^\n]*\n)([^\|\n])', r'\1\n\2', text)
    return text


def _build_html(report: ReportOutput, chart_paths: list[str]) -> str:
    """Build standalone HTML from report."""
    import markdown as md

    sections_html = ""
    for section in report.sections:
        content = _ensure_table_spacing(section.content)
        body = md.markdown(content, extensions=["tables", "fenced_code", "nl2br"])
        sources_links = "".join(
            f'<li><a href="{s}" target="_blank">{s}</a></li>' for s in section.sources
        )
        sources_block = f'<div class="sources"><strong>Sources</strong><ul>{sources_links}</ul></div>' if sources_links else ""
        sections_html += f"<section><h2>{section.title}</h2>{body}{sources_block}</section>\n"

    chart_images = ""
    for cp in chart_paths:
        fname = Path(cp).name
        chart_images += f'<figure><img src="charts/{fname}" alt="Chart" style="max-width:100%;border-radius:4px;"></figure>\n'

    exec_html = md.markdown(_ensure_table_spacing(report.executive_summary), extensions=["tables", "nl2br"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report.title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Georgia', serif; max-width: 960px; margin: 0 auto; padding: 48px 40px; color: #1a1a1a; line-height: 1.7; background: #fff; }}
  h1 {{ font-family: Arial, sans-serif; color: #003A70; font-size: 2em; border-bottom: 3px solid #0071CE; padding-bottom: 16px; margin-bottom: 24px; line-height: 1.3; }}
  h2 {{ font-family: Arial, sans-serif; color: #003A70; font-size: 1.35em; margin-top: 2.5em; margin-bottom: 0.75em; padding-bottom: 6px; border-bottom: 1px solid #cce0f5; }}
  h3 {{ font-family: Arial, sans-serif; color: #005A9C; font-size: 1.1em; margin-top: 1.5em; margin-bottom: 0.5em; }}
  p {{ margin-bottom: 1em; }}
  ul, ol {{ margin: 0.75em 0 1em 1.5em; }}
  li {{ margin-bottom: 0.4em; }}
  .executive-summary {{ background: #f0f6fd; padding: 28px 32px; border-left: 5px solid #0071CE; margin: 28px 0 40px; border-radius: 0 4px 4px 0; }}
  .executive-summary h3 {{ color: #003A70; margin-top: 0; margin-bottom: 12px; font-size: 1em; text-transform: uppercase; letter-spacing: 0.08em; }}
  table {{ border-collapse: collapse; width: 100%; margin: 20px 0; font-size: 0.9em; font-family: Arial, sans-serif; }}
  thead th {{ background: #003A70; color: #fff; padding: 10px 14px; text-align: left; font-weight: 600; }}
  tbody tr:nth-child(even) {{ background: #f4f8fc; }}
  tbody tr:hover {{ background: #e8f0fa; }}
  td {{ border: 1px solid #d5e3f0; padding: 9px 14px; vertical-align: top; }}
  th {{ border: 1px solid #003A70; }}
  section {{ margin-bottom: 48px; }}
  .sources {{ margin-top: 20px; padding: 14px 18px; background: #f9f9f9; border-radius: 4px; font-size: 0.82em; }}
  .sources ul {{ margin: 6px 0 0 1.2em; }}
  .sources li {{ word-break: break-all; margin-bottom: 4px; }}
  a {{ color: #0071CE; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  figure {{ margin: 28px 0; text-align: center; }}
  strong {{ color: #003A70; }}
  code {{ background: #f0f4f8; padding: 2px 5px; border-radius: 3px; font-size: 0.88em; }}
  blockquote {{ border-left: 3px solid #0071CE; margin: 1em 0; padding: 0.5em 1em; color: #444; background: #f8fbff; }}
  @media print {{ body {{ padding: 20px; }} section {{ page-break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>{report.title}</h1>
<div class="executive-summary"><h3>Executive Summary</h3>{exec_html}</div>
{chart_images}
{sections_html}
</body>
</html>"""


def _build_pdf(html_content: str, output_path: str) -> str:
    """Generate PDF from HTML using WeasyPrint."""
    from weasyprint import HTML

    HTML(string=html_content).write_pdf(output_path)
    logger.info(f"PDF saved: {output_path}")
    return output_path


def _build_docx(report: ReportOutput, chart_paths: list[str], output_path: str) -> str:
    """Generate DOCX from report using python-docx."""
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    style = doc.styles["Title"]
    style.font.color.rgb = RGBColor(0, 0x3A, 0x70)

    doc.add_heading(report.title, level=0)

    doc.add_heading("Executive Summary", level=1)
    p = doc.add_paragraph(report.executive_summary)
    p.style.font.size = Pt(11)

    for cp in chart_paths:
        if os.path.exists(cp):
            doc.add_picture(cp, width=Inches(6))
            last_paragraph = doc.paragraphs[-1]
            last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for section in report.sections:
        doc.add_heading(section.title, level=1)

        for block in section.content.split("\n\n"):
            text = block.strip()
            if not text:
                continue

            lines = text.split("\n")
            # Detect markdown table (starts with |)
            if lines[0].startswith("|") and len(lines) >= 2:
                # Parse header and rows (skip separator line)
                rows = [l for l in lines if l.strip() and not set(l.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")) == set()]
                if rows:
                    cols = [c.strip() for c in rows[0].strip("|").split("|")]
                    table = doc.add_table(rows=len(rows), cols=len(cols))
                    table.style = "Table Grid"
                    for ri, row_text in enumerate(rows):
                        cells = [c.strip() for c in row_text.strip("|").split("|")]
                        for ci, cell_text in enumerate(cells[:len(cols)]):
                            cell = table.rows[ri].cells[ci]
                            cell.text = cell_text
                            if ri == 0:
                                for run in cell.paragraphs[0].runs:
                                    run.bold = True
                continue

            if text.startswith("# "):
                doc.add_heading(text.lstrip("# ").strip(), level=2)
            elif text.startswith("## "):
                doc.add_heading(text.lstrip("## ").strip(), level=3)
            elif text.startswith("### "):
                doc.add_heading(text.lstrip("### ").strip(), level=4)
            elif lines[0].startswith("- ") or lines[0].startswith("* "):
                for line in lines:
                    line = line.lstrip("-* ").strip()
                    if line:
                        doc.add_paragraph(line, style="List Bullet")
            else:
                doc.add_paragraph(text)

        if section.sources:
            doc.add_heading("Sources", level=2)
            for src in section.sources:
                doc.add_paragraph(src, style="List Bullet")

    doc.save(output_path)
    logger.info(f"DOCX saved: {output_path}")
    return output_path


@traceable(name="renderer")
async def run_renderer(state: AgentState) -> dict:
    logger.info("Renderer agent started")
    model = get_model(AgentTask.RENDERING)
    session_id = state.get("session_id", state.get("report_id", "default"))
    out_dir = os.path.join(settings.outputs_dir, session_id)
    os.makedirs(out_dir, exist_ok=True)

    results = state.get("research_results", [])
    intake = state.get("intake_result")
    master_prompt = state.get("master_prompt")
    chart_paths = state.get("chart_paths", [])
    summary_msg = next(
        (m for m in state.get("messages", []) if m.get("role") == "summarization"), None
    )

    context = {
        "intake": intake.model_dump() if intake else {},
        "findings": [r.model_dump(mode="json") for r in results],
        "summary": summary_msg["content"] if summary_msg else "",
        "master_prompt": master_prompt.master_prompt if master_prompt else "",
        "available_charts": [Path(p).name for p in chart_paths],
    }

    context_json = json.dumps(context, default=str)
    raw = await _call_llm(SYSTEM_PROMPT, context_json, model)
    if not raw or not raw.strip():
        raise RendererError("LLM returned empty content")
    try:
        parsed = parse_llm_json(raw, context="renderer")
    except ValueError as exc:
        raise RendererError(str(exc)) from exc

    sections = [ReportSection(**s) for s in parsed.get("sections", [])]
    report = ReportOutput(
        id=state.get("report_id", ""),
        title=parsed.get("title", "Untitled Report"),
        executive_summary=parsed.get("executive_summary", ""),
        sections=sections,
        total_cost_usd=state.get("cost_usd", 0),
    )

    html_content = _build_html(report, chart_paths)
    html_path = os.path.join(out_dir, "report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"HTML saved: {html_path}")

    output_paths = [html_path]

    try:
        pdf_path = _build_pdf(html_content, os.path.join(out_dir, "report.pdf"))
        output_paths.append(pdf_path)
    except Exception as e:
        logger.warning(f"PDF generation failed, skipping optional PDF output: {e}")

    try:
        docx_path = _build_docx(report, chart_paths, os.path.join(out_dir, "report.docx"))
        output_paths.append(docx_path)
    except Exception as e:
        logger.error(f"DOCX generation failed: {e}")

    cost = estimate_cost(AgentTask.RENDERING, len(context_json) // 4, len(raw) // 4)
    logger.info(f"Renderer produced report with {len(sections)} sections, {len(output_paths)} files")

    return {
        "report": report,
        "final_report_paths": output_paths,
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "renderer",
        "status": "rendering",
    }
