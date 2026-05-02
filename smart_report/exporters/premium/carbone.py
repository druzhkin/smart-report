"""Carbone Cloud renderer for premium report documents.

Carbone is used here as a production template/conversion engine. The analytic
pipeline still produces a renderer-neutral ``PremiumReportDocument``; this
module flattens it into JSON and merges it into a Carbone HTML template.
"""

from __future__ import annotations

import base64
import html
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .models import PremiumPage, PremiumPreparedBlock, PremiumReportDocument

DEFAULT_CARBONE_API_URL = "https://api.carbone.io"
DEFAULT_TEMPLATE_PATH = Path(__file__).with_name("templates") / "carbone_publication.html"


class CarboneRenderError(RuntimeError):
    """Raised when Carbone export cannot be completed."""


def get_carbone_renderer_status(
    *,
    template_path: Path | None = None,
    api_token: str | None = None,
    api_url: str | None = None,
) -> dict[str, Any]:
    """Return non-secret availability metadata for the Carbone backend."""

    template = template_path or DEFAULT_TEMPLATE_PATH
    token_present = bool(
        (api_token or os.environ.get("CARBONE_API_KEY") or os.environ.get("CARBONE_TOKEN") or "").strip()
    )
    template_exists = template.exists()
    available = token_present and template_exists
    blockers = []
    if not token_present:
        blockers.append("missing_api_token")
    if not template_exists:
        blockers.append("missing_template")
    return {
        "backend": "carbone_cloud",
        "format": "pdf",
        "available": available,
        "blockers": blockers,
        "template": str(template),
        "api_url": (api_url or DEFAULT_CARBONE_API_URL).rstrip("/"),
        "secrets_present": {"api_token": token_present},
    }


def render_premium_carbone_pdf(
    document: PremiumReportDocument,
    path: Path,
    *,
    template_path: Path | None = None,
    api_token: str | None = None,
    api_url: str | None = None,
    timeout_s: float = 120.0,
) -> Path:
    """Render a premium PDF through Carbone Cloud.

    Requires ``CARBONE_API_KEY`` or ``CARBONE_TOKEN`` unless ``api_token`` is
    passed explicitly by a caller/test. The token is never persisted.
    """

    token = (api_token or os.environ.get("CARBONE_API_KEY") or os.environ.get("CARBONE_TOKEN") or "").strip()
    if not token:
        raise CarboneRenderError(
            "CARBONE_API_KEY env var is not set; premium Carbone export is unavailable"
        )

    template = (template_path or DEFAULT_TEMPLATE_PATH).read_bytes()
    payload = {
        "data": to_carbone_data(document),
        "convertTo": "pdf",
        "converter": "C",
        "template": base64.b64encode(template).decode("ascii"),
        "reportName": path.name,
    }
    endpoint = f"{(api_url or DEFAULT_CARBONE_API_URL).rstrip('/')}/render/template?download=true"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "carbone-version": "5",
    }

    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
            response = client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _safe_response_text(exc.response)
        raise CarboneRenderError(
            f"Carbone render failed with HTTP {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise CarboneRenderError(f"Carbone render failed: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return path


def to_carbone_data(document: PremiumReportDocument) -> dict[str, Any]:
    """Flatten ``PremiumReportDocument`` into template-friendly JSON."""

    sections = [
        {
            "index": idx,
            "title": section.title,
            "purpose": section.purpose,
            "blocksHtml": _blocks_html(section.blocks),
        }
        for idx, section in enumerate(document.sections, start=1)
    ]
    appendices = [
        {
            "index": idx,
            "title": appendix.title,
            "purpose": appendix.purpose,
            "blocksHtml": _blocks_html(appendix.blocks),
        }
        for idx, appendix in enumerate(document.appendices, start=1)
    ]
    exhibits = [
        {
            "index": idx,
            "title": block.title,
            "kind": str(block.kind).replace("_", " ").title(),
            "html": _block_html(block),
        }
        for idx, block in enumerate(_exhibit_blocks(document), start=1)
    ]
    readiness = document.premium_readiness or {}
    return {
        "title": document.title,
        "subtitle": document.subtitle,
        "decisionContext": document.plan.decision_context,
        "reportType": str(document.plan.report_type).replace("_", " ").title(),
        "audience": str(document.plan.audience).replace("_", " ").title(),
        "sourceCount": document.source_count,
        "numericFactCount": document.numeric_fact_count,
        "readinessStatus": "Client-ready" if readiness.get("ready") else "Draft / review required",
        "readinessScore": readiness.get("score", "n/a"),
        "heroKpis": _hero_kpis(document),
        "priceChart": _price_chart(document),
        "visualPages": [_page_data(page, idx) for idx, page in enumerate(document.pages, start=1)],
        "sections": sections,
        "appendices": appendices,
        "exhibits": exhibits,
    }


def _page_data(page: PremiumPage, index: int) -> dict[str, Any]:
    visual_type = page.visual.visual_type if page.visual else "none"
    source_notes = page.source_notes or (page.visual.source_notes if page.visual else [])
    return {
        "index": index,
        "pageType": page.page_type.replace("_", " ").title(),
        "visualType": str(visual_type).replace("_", " ").title(),
        "thesis": _clean_cell(page.thesis, limit=140),
        "narrative": _clean_cell(page.narrative, limit=680),
        "implication": _clean_cell(page.implication, limit=360),
        "sourceNote": _source_note(source_notes),
        "chartFrameClass": "" if _page_has_chart(page) else "is-hidden",
        "kpiClass": "" if visual_type == "hero_kpi_strip" else "is-hidden",
        "tableClass": "" if _page_table_html(page) else "is-hidden",
        "bodyClass": "" if _page_body_html(page) else "is-hidden",
        "chart": _page_chart(page),
        "tableHtml": _page_table_html(page),
        "bodyHtml": _page_body_html(page),
        "kpiHtml": _page_kpi_html(page),
        "kpis": _page_kpis(page),
    }


def _page_has_chart(page: PremiumPage) -> bool:
    if not page.visual:
        return False
    return page.visual.visual_type in {
        "ranking_bar",
        "time_series",
        "distribution",
        "evidence_quality",
        "waterfall",
    }


def _page_body_html(page: PremiumPage) -> str:
    if not page.visual or page.visual.visual_type != "narrative_text":
        return ""
    body = str(page.visual.data.get("body") or page.narrative or "")
    return _rich_text_html(body, limit=2600)


def _source_note(notes: list[str]) -> str:
    cleaned = [_clean_cell(note, limit=72) for note in notes if str(note or "").strip()]
    if not cleaned:
        return "Source: Smart Report analysis."
    return "Source: " + "; ".join(cleaned[:4])


def _page_kpis(page: PremiumPage) -> list[dict[str, str]]:
    if not page.visual or page.visual.visual_type != "hero_kpi_strip":
        return []
    items = page.visual.data.get("items", [])
    if not isinstance(items, list):
        return []
    cards = []
    for item in items[:6]:
        if not isinstance(item, dict):
            continue
        cards.append(
            {
                "value": _clean_cell(item.get("value", ""), limit=28),
                "label": _clean_cell(item.get("label", ""), limit=58),
                "source": _clean_cell(item.get("source", ""), limit=42),
            }
        )
    return cards


def _page_kpi_html(page: PremiumPage) -> str:
    cards = _page_kpis(page)
    if not cards:
        return ""
    parts = []
    for card in cards:
        parts.append(
            '<div class="insight">'
            f"<strong>{html.escape(card['value'])}</strong>"
            f"<span>{html.escape(card['label'])}</span>"
            f"<span>{html.escape(card['source'])}</span>"
            "</div>"
        )
    return "".join(parts)


def _page_table_html(page: PremiumPage) -> str:
    if not page.visual or page.visual.visual_type not in {
        "source_table",
        "scenario_matrix",
        "risk_heatmap",
    }:
        return ""
    data = page.visual.data
    if page.visual.visual_type == "risk_heatmap":
        columns = ["Topic", "Importance", "Source A", "Source B", "Resolution"]
        rows = [
            [
                row.get("topic", ""),
                row.get("importance", ""),
                row.get("source_a", ""),
                row.get("source_b", ""),
                row.get("resolution", ""),
            ]
            for row in data.get("rows", [])
            if isinstance(row, dict)
        ]
    else:
        columns = data.get("columns", [])
        rows = data.get("rows", [])
    if not isinstance(columns, list) or not isinstance(rows, list):
        return ""
    block = PremiumPreparedBlock(
        kind="appendix_table",
        title=page.visual.title,
        columns=[str(col) for col in columns],
        rows=[[str(cell) for cell in row] for row in rows if isinstance(row, list)],
    )
    return _table_html(block)


def _page_chart(page: PremiumPage) -> dict[str, Any]:
    if not page.visual:
        return _empty_chart()
    visual_type = page.visual.visual_type
    data = page.visual.data
    if visual_type == "hero_kpi_strip":
        return _empty_chart()
    if visual_type == "evidence_quality":
        return _chart_from_points(
            data.get("points", []),
            title=page.visual.title,
            orientation="vertical",
            color="#2dbf6a",
        )
    if visual_type in {"ranking_bar", "distribution", "waterfall"}:
        points = data.get("points")
        if points:
            return _chart_from_points(points, title=page.visual.title, orientation="horizontal")
        if "chart_type" in data:
            return _chart_from_chart_spec(data)
    if visual_type == "time_series":
        return _chart_from_chart_spec(data)
    return _empty_chart()


def _chart_from_chart_spec(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("data", {})
    if not isinstance(raw, dict):
        return _empty_chart()
    points = raw.get("points") or raw.get("series") or raw.get("data")
    if not points and {"labels", "values"} <= set(raw):
        points = [
            {"label": label, "value": value}
            for label, value in zip(raw.get("labels", []), raw.get("values", []), strict=False)
        ]
    if not isinstance(points, list):
        return _empty_chart()
    title = str(data.get("title") or "Chart")
    if data.get("chart_type") == "scatter":
        return _scatter_chart_from_points(
            points,
            title=title,
            x_label=str(data.get("x_label") or ""),
            y_label=str(data.get("y_label") or ""),
        )
    if data.get("chart_type") == "line":
        return _line_chart_from_points(points, title=title)
    return _chart_from_points(points, title=title, orientation="horizontal")


def _scatter_chart_from_points(
    points: list[object],
    *,
    title: str,
    x_label: str,
    y_label: str,
) -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        x_value = _number_from_text(point.get("x"))
        y_value = _number_from_text(point.get("y"))
        label = _clean_cell(point.get("label", ""), limit=34)
        if x_value is None or y_value is None:
            continue
        parsed.append({"value": [x_value, y_value], "label": label})
    if not parsed:
        return _empty_chart()
    return {
        "type": "echarts@v5a",
        "width": 920,
        "height": 430,
        "option": {
            "animation": False,
            "title": {"text": title, "left": 0, "textStyle": {"fontSize": 16, "fontWeight": 500}},
            "grid": {"left": 64, "right": 44, "top": 58, "bottom": 70},
            "textStyle": {"fontFamily": "Arial", "color": "#171a1f"},
            "xAxis": {
                "type": "value",
                "name": x_label,
                "nameLocation": "middle",
                "nameGap": 42,
                "axisLabel": {"fontSize": 10, "color": "#535b66"},
                "splitLine": {"lineStyle": {"color": "#e6e8eb"}},
            },
            "yAxis": {
                "type": "value",
                "name": y_label,
                "nameLocation": "middle",
                "nameGap": 44,
                "axisLabel": {"fontSize": 10, "color": "#535b66"},
                "splitLine": {"lineStyle": {"color": "#e6e8eb"}},
            },
            "series": [
                {
                    "type": "scatter",
                    "data": parsed,
                    "symbolSize": 18,
                    "itemStyle": {"color": "#d33f2f"},
                    "label": {
                        "show": True,
                        "formatter": "{b}",
                        "position": "right",
                        "fontSize": 10,
                        "color": "#171a1f",
                    },
                }
            ],
        },
    }


def _line_chart_from_points(points: list[object], *, title: str) -> dict[str, Any]:
    parsed: list[tuple[str, float]] = []
    for point in points:
        if isinstance(point, dict):
            label = _clean_cell(point.get("label") or point.get("x") or point.get("date"), limit=34)
            value = _number_from_text(point.get("value") or point.get("y"))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            label = _clean_cell(point[0], limit=34)
            value = _number_from_text(point[1])
        else:
            continue
        if label and value is not None:
            parsed.append((label, value))
    if not parsed:
        return _empty_chart()
    labels = [label for label, _ in parsed[:12]]
    values = [value for _, value in parsed[:12]]
    return {
        "type": "echarts@v5a",
        "width": 920,
        "height": 430,
        "option": {
            "animation": False,
            "title": {"text": title, "left": 0, "textStyle": {"fontSize": 16, "fontWeight": 500}},
            "grid": {"left": 58, "right": 38, "top": 56, "bottom": 74},
            "textStyle": {"fontFamily": "Arial", "color": "#171a1f"},
            "xAxis": {
                "type": "category",
                "data": labels,
                "boundaryGap": False,
                "axisLabel": {"fontSize": 10, "color": "#535b66", "rotate": 0},
                "axisLine": {"lineStyle": {"color": "#cfd4da"}},
            },
            "yAxis": {
                "type": "value",
                "axisLabel": {"fontSize": 10, "color": "#535b66"},
                "splitLine": {"lineStyle": {"color": "#e6e8eb"}},
            },
            "series": [
                {
                    "type": "line",
                    "data": values,
                    "smooth": True,
                    "symbolSize": 7,
                    "lineStyle": {"width": 4, "color": "#d33f2f"},
                    "itemStyle": {"color": "#d33f2f"},
                    "areaStyle": {"color": "rgba(211, 63, 47, 0.12)"},
                    "label": {"show": True, "position": "top", "fontSize": 10, "color": "#171a1f"},
                }
            ],
        },
    }


def _chart_from_points(
    points: object,
    *,
    title: str,
    orientation: str = "horizontal",
    color: str = "#d33f2f",
) -> dict[str, Any]:
    if not isinstance(points, list):
        return _empty_chart()
    parsed: list[tuple[str, float]] = []
    for point in points:
        if isinstance(point, dict):
            label = _clean_cell(point.get("label", ""), limit=56)
            value = _number_from_text(point.get("value", ""))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            label = _clean_cell(point[0], limit=56)
            value = _number_from_text(point[1])
        else:
            continue
        if label and value is not None:
            parsed.append((label, value))
    if not parsed:
        return _empty_chart()
    labels = [label for label, _ in parsed[:10]]
    values = [value for _, value in parsed[:10]]
    horizontal = orientation == "horizontal"
    return {
        "type": "echarts@v5a",
        "width": 920,
        "height": 430,
        "option": {
            "animation": False,
            "title": {"text": title, "left": 0, "textStyle": {"fontSize": 16, "fontWeight": 500}},
            "grid": {
                "left": 260 if horizontal else 52,
                "right": 42,
                "top": 52,
                "bottom": 48 if horizontal else 86,
            },
            "textStyle": {"fontFamily": "Arial", "color": "#171a1f"},
            "xAxis": {
                "type": "value" if horizontal else "category",
                "data": None if horizontal else labels,
                "axisLabel": {"fontSize": 10, "color": "#535b66", "rotate": 0 if horizontal else 25},
                "splitLine": {"lineStyle": {"color": "#e6e8eb"}},
            },
            "yAxis": {
                "type": "category" if horizontal else "value",
                "data": labels if horizontal else None,
                "axisLabel": {"fontSize": 10, "color": "#535b66"},
                "axisLine": {"lineStyle": {"color": "#cfd4da"}},
            },
            "series": [
                {
                    "type": "bar",
                    "data": values,
                    "barMaxWidth": 28,
                    "itemStyle": {"color": color},
                    "label": {
                        "show": True,
                        "position": "right" if horizontal else "top",
                        "fontSize": 10,
                        "color": "#171a1f",
                    },
                }
            ],
        },
    }


def _empty_chart() -> dict[str, Any]:
    return {
        "type": "echarts@v5a",
        "width": 1,
        "height": 1,
        "option": {"xAxis": {"show": False}, "yAxis": {"show": False}, "series": []},
    }


def _blocks_html(blocks: list[PremiumPreparedBlock]) -> str:
    return "\n".join(_block_html(block) for block in blocks)


def _block_html(block: PremiumPreparedBlock) -> str:
    heading = html.escape(block.title)
    kind = html.escape(str(block.kind).replace("_", " ").upper())
    parts = [f'<section class="block"><div class="eyebrow">{kind}</div><h3>{heading}</h3>']
    if block.body:
        parts.append(f"<p>{html.escape(_clean_cell(block.body, limit=900))}</p>")
    if block.rows:
        parts.append(_table_html(block))
    if block.notes:
        note_items = "".join(f"<li>{html.escape(note)}</li>" for note in block.notes)
        parts.append(f'<ul class="notes">{note_items}</ul>')
    parts.append("</section>")
    return "".join(parts)


def _table_html(block: PremiumPreparedBlock) -> str:
    columns = block.columns or ["Item", "Value"]
    header = "".join(f"<th>{html.escape(str(col))}</th>" for col in columns)
    rows = []
    for row in block.rows[:18]:
        cells = []
        for idx in range(len(columns)):
            value = row[idx] if idx < len(row) else ""
            cells.append(f"<td>{html.escape(_clean_cell(value))}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _exhibit_blocks(document: PremiumReportDocument) -> list[PremiumPreparedBlock]:
    preferred = {
        "kpi_grid",
        "evidence_table",
        "source_quality_table",
        "scenario_matrix",
        "sensitivity_table",
        "decision_matrix",
        "risk_register",
        "competitive_matrix",
    }
    blocks: list[PremiumPreparedBlock] = []
    seen: set[str] = set()
    for section in [*document.sections, *document.appendices]:
        for block in section.blocks:
            if block.kind not in preferred:
                continue
            key = f"{block.kind}:{block.title}"
            if key in seen:
                continue
            seen.add(key)
            blocks.append(block)
    return blocks[: max(document.plan.publication.min_exhibit_pages, 4)]


def _hero_kpis(document: PremiumReportDocument) -> list[dict[str, str]]:
    for section in document.sections:
        for block in section.blocks:
            if block.kind != "kpi_grid" or not block.rows:
                continue
            cards = []
            for row in block.rows[:6]:
                cards.append(
                    {
                        "label": _clean_cell(row[0] if len(row) > 0 else "", limit=52),
                        "value": _clean_cell(row[1] if len(row) > 1 else "", limit=32),
                        "subject": _clean_cell(row[2] if len(row) > 2 else "", limit=70),
                        "source": _clean_cell(row[3] if len(row) > 3 else "", limit=42),
                    }
                )
            return cards
    return [
        {
            "label": "Sources",
            "value": str(document.source_count),
            "subject": "Evidence base",
            "source": "Smart Report",
        },
        {
            "label": "Numeric facts",
            "value": str(document.numeric_fact_count),
            "subject": "Fact register",
            "source": "Smart Report",
        },
    ]


def _price_chart(document: PremiumReportDocument) -> dict[str, Any]:
    points: list[tuple[str, float]] = []
    seen: set[str] = set()
    for section in document.sections:
        for block in section.blocks:
            if block.kind != "kpi_grid":
                continue
            for row in block.rows:
                if len(row) < 3:
                    continue
                label = _clean_cell(row[2], limit=44)
                value = _number_from_text(row[1])
                metric = str(row[0]).lower()
                is_price_metric = "price" in metric or "\u0446\u0435\u043d" in metric
                if value is None or not label or not is_price_metric:
                    continue
                key = f"{label}:{value}"
                if key in seen:
                    continue
                points.append((label, value))
                seen.add(key)
                if len(points) >= 8:
                    break
        if len(points) >= 8:
            break
    if len(points) < 2:
        points = [
            ("Sources", float(document.source_count)),
            ("Facts", float(document.numeric_fact_count)),
        ]
    labels = [label for label, _ in points]
    values = [value for _, value in points]
    return {
        "type": "echarts@v5a",
        "width": 920,
        "height": 420,
        "option": {
            "animation": False,
            "grid": {"left": 260, "right": 32, "top": 28, "bottom": 38},
            "textStyle": {"fontFamily": "Arial", "color": "#171a1f"},
            "xAxis": {
                "type": "value",
                "axisLabel": {"fontSize": 11, "color": "#535b66"},
                "splitLine": {"lineStyle": {"color": "#e6e8eb"}},
            },
            "yAxis": {
                "type": "category",
                "data": labels,
                "axisLabel": {"fontSize": 10, "color": "#535b66"},
                "axisLine": {"lineStyle": {"color": "#cfd4da"}},
            },
            "series": [
                {
                    "name": "Value",
                    "type": "bar",
                    "data": values,
                    "barMaxWidth": 26,
                    "itemStyle": {"color": "#d33f2f"},
                    "label": {
                        "show": True,
                        "position": "right",
                        "fontSize": 10,
                        "color": "#171a1f",
                    },
                },
            ],
        },
    }


def _clean_cell(value: object, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    text = (
        text.replace("[STRONG]", "")
        .replace("[MODERATE]", "")
        .replace("[WEAK]", "")
        .replace("[SPECULATIVE]", "")
    )
    text = " ".join(text.split())
    while "[REF:" in text:
        start = text.find("[REF:")
        end = text.find("]", start)
        if end == -1:
            break
        ref = text[start + 5 : end]
        short_ref = _short_url(ref)
        text = f"{text[:start]}({short_ref}){text[end + 1:]}"
    if text.startswith("http://") or text.startswith("https://"):
        text = _short_url(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip(" ,.;:") + "..."


def _rich_text_html(value: object, *, limit: int) -> str:
    text = _clean_cell(value, limit=limit)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n|(?<=\.)\s+(?=\[|[А-ЯA-Z])", text) if part.strip()]
    html_parts = []
    for paragraph in paragraphs[:8]:
        if paragraph.startswith("## "):
            html_parts.append(f"<h3>{html.escape(paragraph[3:].strip())}</h3>")
            continue
        if paragraph.startswith("- "):
            items = [item.strip("- ").strip() for item in paragraph.split("\n") if item.strip()]
            html_parts.append("<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>")
            continue
        html_parts.append(f"<p>{html.escape(paragraph)}</p>")
    return "".join(html_parts)


def _number_from_text(value: object) -> float | None:
    text = str(value or "").replace("\xa0", " ")
    match = re.search(r"-?\d+(?:[ ,.]\d+)?", text)
    if not match:
        return None
    normalized = match.group(0).replace(" ", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _short_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError:
        return value[:80]
    host = parsed.netloc.replace("www.", "")
    path = parsed.path.strip("/")
    if not host:
        return value[:80]
    if not path:
        return host
    first = path.split("/", 1)[0]
    return f"{host}/{first}"


def _safe_response_text(response: httpx.Response) -> str:
    text = response.text.strip()
    if not text:
        return "<empty response>"
    return text[:500]
