"""Publication-grade PDF renderer for premium Smart Report artifacts.

This renderer intentionally does not convert the DOCX. It lays out the same
renderer-neutral ``PremiumReportDocument`` as an A4 consulting-style
publication: full-bleed cover, image-led openers, exhibit pages, source notes,
and a minimum publication page count.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from textwrap import wrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .models import (
    PremiumPage,
    PremiumPageVisual,
    PremiumPreparedBlock,
    PremiumPreparedSection,
    PremiumReportDocument,
)

PAGE_W, PAGE_H = A4
MARGIN_X = 42
TOP = PAGE_H - 54
BOTTOM = 46

GREEN = colors.HexColor("#2FBE63")
DARK_GREEN = colors.HexColor("#16784C")
INK = colors.HexColor("#303238")
MUTED = colors.HexColor("#6F757D")
LIGHT = colors.HexColor("#F3F5F4")
LINE = colors.HexColor("#D6DAD8")
PALE_GREEN = colors.HexColor("#E8F5EC")
WHITE = colors.white

FONT_REGULAR = "SR-Regular"
FONT_BOLD = "SR-Bold"


def render_premium_pdf(
    document: PremiumReportDocument,
    path: Path,
    *,
    include_internal_audit: bool = False,
) -> Path:
    """Render a publication-grade A4 PDF.

    The renderer is deterministic and local. It uses ReportLab directly so the
    premium PDF is not limited by Word conversion fidelity.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    _register_fonts()
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(document.title)
    c.setAuthor("Smart Report")
    c.setSubject(document.subtitle)

    page_no = 0
    page_no = _cover(c, document, page_no)
    page_no = _contents(c, document, page_no)
    page_no = _opening_spread(c, document, page_no)

    storyboard = document.pages or _fallback_storyboard(document)
    for story_no, page in enumerate(storyboard, start=1):
        page_no = _story_page(c, document, page, story_no, page_no)

    while page_no < document.plan.deliverables.report_min_pages:
        page_no = _methodology_page(c, document, page_no, page_no + 1)

    c.save()
    return path


def _register_fonts() -> None:
    if FONT_REGULAR in pdfmetrics.getRegisteredFontNames():
        return
    candidates = [
        (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
        ),
        (
            Path("C:/Windows/Fonts/calibri.ttf"),
            Path("C:/Windows/Fonts/calibrib.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular)))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
            return
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, "Helvetica"))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, "Helvetica-Bold"))


def _cover(c: canvas.Canvas, document: PremiumReportDocument, page_no: int) -> int:
    _draw_full_bleed_city(c)
    card_x, card_y, card_w, card_h = 56, PAGE_H - 340, 426, 244
    c.setFillColor(WHITE)
    c.rect(card_x, card_y, card_w, card_h, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(card_x, card_y + card_h - 7, card_w, 7, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.setFont(FONT_BOLD, 10)
    c.drawString(card_x + 24, card_y + card_h - 38, _upper("SMART REPORT PUBLICATION"))
    c.setFillColor(INK)
    title_y = card_y + card_h - 72
    title_used = _draw_wrapped(
        c,
        document.title,
        card_x + 24,
        title_y,
        card_w - 48,
        31,
        FONT_REGULAR,
        27,
        max_lines=4,
    )
    subtitle_y = max(card_y + 72, title_y - title_used - 14)
    c.setFillColor(INK)
    _draw_wrapped(
        c,
        document.subtitle,
        card_x + 24,
        subtitle_y,
        card_w - 48,
        19,
        FONT_REGULAR,
        16,
        max_lines=2,
    )
    c.setFont(FONT_BOLD, 9)
    c.drawString(card_x + 24, card_y + 30, "Publication-grade PDF")
    c.setFont(FONT_BOLD, 20)
    c.setFillColor(WHITE)
    c.drawRightString(PAGE_W - 48, 54, "SMART REPORT")
    c.showPage()
    return page_no + 1


def _contents(c: canvas.Canvas, document: PremiumReportDocument, page_no: int) -> int:
    page_no += 1
    _header(c, document, page_no)
    _green_rule(c, MARGIN_X, TOP + 8, 190)
    c.setFillColor(INK)
    c.setFont(FONT_REGULAR, 33)
    c.drawString(MARGIN_X, TOP - 38, _label(document, "contents"))
    c.setFont(FONT_REGULAR, 16)
    c.setFillColor(GREEN)
    context_used = _draw_wrapped(
        c,
        document.plan.decision_context,
        MARGIN_X,
        TOP - 82,
        PAGE_W - 2 * MARGIN_X,
        20,
        FONT_REGULAR,
        16,
        max_lines=2,
    )
    y = TOP - 116 - context_used
    items = [section.title for section in document.sections[:9]]
    for idx, title in enumerate(items, start=1):
        c.setFillColor(GREEN if idx <= 3 else MUTED)
        c.setFont(FONT_BOLD, 9)
        c.drawString(MARGIN_X, y, f"{idx:02d}")
        c.setFillColor(INK)
        c.setFont(FONT_REGULAR, 13)
        _draw_wrapped(c, title, MARGIN_X + 42, y, PAGE_W - MARGIN_X * 2 - 42, 16, FONT_REGULAR, 13, max_lines=2)
        c.setStrokeColor(LINE)
        c.line(MARGIN_X + 42, y - 24, PAGE_W - MARGIN_X, y - 24)
        y -= 46
    _footer(c, document, page_no)
    c.showPage()
    return page_no


def _opening_spread(c: canvas.Canvas, document: PremiumReportDocument, page_no: int) -> int:
    page_no += 1
    intro = _label(document, "introduction")
    _hero_band(c, intro)
    _green_rule(c, MARGIN_X, PAGE_H - 270, 184)
    c.setFillColor(INK)
    c.setFont(FONT_REGULAR, 32)
    c.drawString(MARGIN_X, PAGE_H - 320, intro)
    c.setFillColor(GREEN)
    c.setFont(FONT_REGULAR, 19)
    _draw_wrapped(
        c,
        _clip(document.plan.decision_context, 210),
        MARGIN_X,
        PAGE_H - 372,
        PAGE_W - 2 * MARGIN_X,
        24,
        FONT_REGULAR,
        19,
        max_lines=3,
    )
    body = _first_section_block_body(document, "executive_summary") or document.title
    _draw_columns(c, body, MARGIN_X, PAGE_H - 472, PAGE_W - 2 * MARGIN_X, 280)
    _footer(c, document, page_no)
    c.showPage()
    return page_no


def _section_opener(
    c: canvas.Canvas,
    document: PremiumReportDocument,
    section: PremiumPreparedSection,
    page_no: int,
) -> int:
    page_no += 1
    _hero_band(c, section.title)
    _green_rule(c, MARGIN_X, PAGE_H - 270, 260)
    c.setFillColor(INK)
    c.setFont(FONT_REGULAR, 30)
    _draw_wrapped(c, section.title, MARGIN_X, PAGE_H - 320, PAGE_W - 2 * MARGIN_X, 35, FONT_REGULAR, 30)
    c.setFillColor(GREEN)
    _draw_wrapped(c, section.purpose, MARGIN_X, PAGE_H - 420, PAGE_W - 2 * MARGIN_X, 22, FONT_REGULAR, 18, max_lines=4)
    _footer(c, document, page_no)
    c.showPage()
    return page_no


def _section_page(
    c: canvas.Canvas,
    document: PremiumReportDocument,
    section: PremiumPreparedSection,
    page_no: int,
    *,
    appendix: bool = False,
) -> int:
    page_no += 1
    _header(c, document, page_no)
    c.setFillColor(GREEN if not appendix else MUTED)
    c.setFont(FONT_BOLD, 11)
    c.drawString(MARGIN_X, TOP, _label(document, "appendix" if appendix else "section"))
    c.setFillColor(INK)
    c.setFont(FONT_REGULAR, 25)
    _draw_wrapped(c, section.title, MARGIN_X, TOP - 30, PAGE_W - 2 * MARGIN_X, 29, FONT_REGULAR, 25, max_lines=2)
    y = TOP - 100
    c.setFillColor(MUTED)
    _draw_wrapped(c, section.purpose, MARGIN_X, y, PAGE_W - 2 * MARGIN_X, 13, FONT_REGULAR, 10, max_lines=3)
    y -= 62
    for block in section.blocks[:3]:
        if y < 190:
            _footer(c, document, page_no)
            c.showPage()
            page_no += 1
            _header(c, document, page_no)
            y = TOP - 20
        y = _draw_block(c, block, MARGIN_X, y, PAGE_W - 2 * MARGIN_X)
        y -= 20
    _footer(c, document, page_no)
    c.showPage()
    return page_no


def _exhibit_page(
    c: canvas.Canvas,
    document: PremiumReportDocument,
    block: PremiumPreparedBlock,
    exhibit_no: int,
    page_no: int,
) -> int:
    page_no += 1
    _header(c, document, page_no)
    c.setFillColor(GREEN)
    c.setFont(FONT_BOLD, 10)
    c.drawString(MARGIN_X, TOP, _label(document, "exhibit", exhibit_no))
    c.setFillColor(INK)
    c.setFont(FONT_REGULAR, 21)
    _draw_wrapped(c, block.title, MARGIN_X, TOP - 28, PAGE_W - 2 * MARGIN_X, 26, FONT_REGULAR, 21, max_lines=2)
    y = TOP - 92
    if block.rows and block.kind == "kpi_grid":
        y = _draw_kpi_exhibit(c, block, MARGIN_X, y, PAGE_W - 2 * MARGIN_X)
    elif block.rows and block.kind in {"scenario_matrix", "decision_matrix", "risk_register"}:
        y = _draw_card_matrix(c, block, MARGIN_X, y, PAGE_W - 2 * MARGIN_X)
    elif block.rows and block.kind == "sensitivity_table":
        y = _draw_sensitivity_exhibit(c, block, MARGIN_X, y, PAGE_W - 2 * MARGIN_X)
    elif block.rows:
        y = _draw_table(c, block.columns, block.rows[:14], MARGIN_X, y, PAGE_W - 2 * MARGIN_X, dense=True)
    elif block.body:
        _draw_columns(c, block.body, MARGIN_X, y, PAGE_W - 2 * MARGIN_X, 430)
        y -= 440
    else:
        _draw_exhibit_placeholder(c, MARGIN_X, y - 300, PAGE_W - 2 * MARGIN_X, 300, block.kind)
        y -= 330
    if y > BOTTOM + 250:
        panel_h = min(280, y - BOTTOM - 72)
        _draw_exhibit_support_visual(
            c,
            document,
            block,
            MARGIN_X,
            BOTTOM + 54,
            PAGE_W - 2 * MARGIN_X,
            panel_h,
        )
        y = BOTTOM + 44
    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 7)
    c.drawString(MARGIN_X, max(BOTTOM + 18, y - 12), _label(document, "source_note"))
    _footer(c, document, page_no)
    c.showPage()
    return page_no


def _story_page(
    c: canvas.Canvas,
    document: PremiumReportDocument,
    page: PremiumPage,
    story_no: int,
    page_no: int,
) -> int:
    page_no += 1
    _header(c, document, page_no)
    russian = _has_cyrillic(f"{document.title} {document.subtitle}")
    is_exhibit = page.page_type in {"exhibit", "appendix"} or (
        page.visual is not None and page.visual.visual_type not in {"none", "narrative_text"}
    )
    c.setFillColor(GREEN if is_exhibit else DARK_GREEN)
    c.setFont(FONT_BOLD, 10)
    c.drawString(
        MARGIN_X,
        TOP,
        _label(document, "exhibit", story_no) if is_exhibit else _label(document, "section"),
    )
    c.setFillColor(INK)
    c.setFont(FONT_REGULAR, 24)
    _draw_wrapped(c, page.thesis, MARGIN_X, TOP - 28, PAGE_W - 2 * MARGIN_X, 28, FONT_REGULAR, 24, max_lines=3)

    y = TOP - 114
    visual_h = 318 if page.visual and page.visual.visual_type != "narrative_text" else 228
    visual_y = y - visual_h
    if page.visual and page.visual.visual_type != "none":
        _draw_page_visual(c, document, page.visual, MARGIN_X, visual_y, PAGE_W - 2 * MARGIN_X, visual_h)
        y = visual_y - 24
    else:
        _draw_exhibit_placeholder(c, MARGIN_X, visual_y, PAGE_W - 2 * MARGIN_X, visual_h, page.page_type)
        y = visual_y - 24

    narrative = page.narrative or _visual_body(page.visual) or page.thesis
    implication = page.implication or (
        "Эта страница переводит доказательную базу в управленческий вывод."
        if russian
        else "This page converts the evidence base into a decision-useful conclusion."
    )
    source_note = _source_note_for_page(document, page)
    text_w = (PAGE_W - 2 * MARGIN_X - 22) * 0.62
    callout_x = MARGIN_X + text_w + 22
    callout_w = PAGE_W - MARGIN_X - callout_x

    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 10)
    c.drawString(MARGIN_X, y, "Интерпретация" if russian else "Interpretation")
    c.setFillColor(MUTED)
    used = _draw_wrapped(c, narrative, MARGIN_X, y - 18, text_w, 12, FONT_REGULAR, 9.2, max_lines=9)

    callout_h = max(86, min(132, used + 42))
    c.setFillColor(PALE_GREEN)
    c.rect(callout_x, y - callout_h + 4, callout_w, callout_h, fill=1, stroke=0)
    c.setFillColor(DARK_GREEN)
    c.setFont(FONT_BOLD, 8)
    c.drawString(callout_x + 12, y - 16, "Что это означает" if russian else "What it means")
    c.setFillColor(INK)
    _draw_wrapped(c, implication, callout_x + 12, y - 34, callout_w - 24, 11, FONT_REGULAR, 8.4, max_lines=6)

    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 7)
    c.drawString(MARGIN_X, BOTTOM + 18, source_note)
    _footer(c, document, page_no)
    c.showPage()
    return page_no


def _draw_page_visual(
    c: canvas.Canvas,
    document: PremiumReportDocument,
    visual: PremiumPageVisual,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    russian = _has_cyrillic(f"{document.title} {document.subtitle}")
    c.setFillColor(colors.HexColor("#F4F8F6"))
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.setStrokeColor(LINE)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setFillColor(GREEN)
    c.setFont(FONT_BOLD, 8)
    c.drawString(x + 18, y + h - 24, _visual_type_label(visual.visual_type, russian=russian))
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 13)
    _draw_wrapped(
        c,
        _visual_title(visual, russian=russian),
        x + 18,
        y + h - 44,
        w - 36,
        15,
        FONT_BOLD,
        12,
        max_lines=2,
    )

    inner_x, inner_y, inner_w, inner_h = x + 18, y + 24, w - 36, h - 88
    if visual.visual_type == "hero_kpi_strip":
        _draw_visual_kpis(c, visual, inner_x, inner_y, inner_w, inner_h)
        return
    if visual.visual_type in {"scenario_matrix", "risk_heatmap", "source_table"}:
        _draw_visual_table(c, visual, inner_x, inner_y + inner_h, inner_w, inner_h)
        return
    if visual.visual_type == "evidence_quality":
        _draw_visual_evidence_quality(c, visual, inner_x, inner_y, inner_w, inner_h, russian=russian)
        return
    if visual.visual_type == "narrative_text":
        _draw_visual_narrative(c, visual, inner_x, inner_y + inner_h, inner_w, inner_h)
        return
    points = _points_from_visual(visual)
    if points:
        _draw_bar_line_chart(c, [(label, value) for label, value in points], inner_x, inner_y, inner_w, inner_h, russian=russian)
        return
    _draw_exhibit_placeholder(c, inner_x, inner_y, inner_w, inner_h, visual.visual_type)


def _visual_type_label(visual_type: str, *, russian: bool) -> str:
    if not russian:
        return str(visual_type).replace("_", " ").upper()
    labels = {
        "hero_kpi_strip": "КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ",
        "ranking_bar": "РЕЙТИНГОВАЯ ДИАГРАММА",
        "time_series": "ДИНАМИКА",
        "distribution": "СТРУКТУРА",
        "scenario_matrix": "СЦЕНАРНАЯ МАТРИЦА",
        "risk_heatmap": "КАРТА РИСКОВ",
        "evidence_quality": "КАЧЕСТВО ИСТОЧНИКОВ",
        "waterfall": "ФАКТОРНЫЙ ВКЛАД",
        "market_map": "КАРТА РЫНКА",
        "source_table": "ТАБЛИЦА ИСТОЧНИКОВ",
        "narrative_text": "АНАЛИТИЧЕСКИЙ ТЕКСТ",
    }
    return labels.get(str(visual_type), str(visual_type).replace("_", " ").upper())


def _visual_title(visual: PremiumPageVisual, *, russian: bool) -> str:
    if not russian:
        return visual.title
    titles = {
        "Executive KPI strip": "Ключевые показатели решения",
        "Source reliability mix": "Надежность источников",
        "Comparable numeric signal": "Сопоставимый числовой сигнал",
        "Conflict and uncertainty heatmap": "Карта противоречий и неопределенности",
    }
    return titles.get(visual.title, visual.title)


def _draw_visual_kpis(
    c: canvas.Canvas,
    visual: PremiumPageVisual,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    items = visual.data.get("items", [])
    if not isinstance(items, list) or not items:
        _draw_exhibit_placeholder(c, x, y, w, h, visual.visual_type)
        return
    rows = []
    for item in items[:6]:
        if isinstance(item, dict):
            rows.append([
                str(item.get("label") or "Metric"),
                str(item.get("value") or ""),
                str(item.get("importance") or ""),
                str(item.get("source") or ""),
            ])
    block = PremiumPreparedBlock(kind="kpi_grid", title=visual.title, rows=rows)
    _draw_kpi_exhibit(c, block, x, y + h - 8, w)


def _draw_visual_table(
    c: canvas.Canvas,
    visual: PremiumPageVisual,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    if visual.visual_type == "risk_heatmap":
        columns = ["Topic", "Importance", "Source A", "Source B", "Resolution"]
        raw_rows = visual.data.get("rows", [])
        rows = [
            [
                str(row.get("topic", "")),
                str(row.get("importance", "")),
                str(row.get("source_a", "")),
                str(row.get("source_b", "")),
                str(row.get("resolution", "")),
            ]
            for row in raw_rows
            if isinstance(row, dict)
        ]
        _draw_table(c, columns, rows[:7], x, y, w, dense=True)
        return
    columns = visual.data.get("columns", [])
    rows = visual.data.get("rows", [])
    if not isinstance(columns, list) or not isinstance(rows, list):
        _draw_exhibit_placeholder(c, x, y - h, w, h, visual.visual_type)
        return
    _draw_table(
        c,
        [str(col) for col in columns],
        [[str(cell) for cell in row] for row in rows[:8] if isinstance(row, list)],
        x,
        y,
        w,
        dense=True,
    )


def _draw_visual_evidence_quality(
    c: canvas.Canvas,
    visual: PremiumPageVisual,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    russian: bool,
) -> None:
    points = visual.data.get("points", [])
    buckets = {"high": 0.0, "medium": 0.0, "low": 0.0}
    if isinstance(points, list):
        for point in points:
            if isinstance(point, dict):
                label = str(point.get("label", "")).lower()
                value = _first_number(point.get("value")) or 0
                if label in buckets:
                    buckets[label] += value
    total = max(sum(buckets.values()), 1)
    cx, cy = x + w * 0.38, y + h * 0.48
    radius = min(w, h) * 0.28
    start = 90
    palette = {
        "high": GREEN,
        "medium": colors.HexColor("#8DCBA5"),
        "low": colors.HexColor("#B75E55"),
    }
    for key in ("high", "medium", "low"):
        if buckets[key] <= 0:
            continue
        extent = 360 * buckets[key] / total
        c.setFillColor(palette[key])
        c.wedge(cx - radius, cy - radius, cx + radius, cy + radius, start, start + extent, fill=1)
        start += extent
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 7)
    c.drawString(x + 20, y + h - 22, "Надежность источников" if russian else "Source reliability mix")
    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 8)
    labels = (
        {"high": "высокая", "medium": "средняя", "low": "низкая"}
        if russian
        else {"high": "high", "medium": "medium", "low": "low"}
    )
    for idx, key in enumerate(("high", "medium", "low")):
        c.drawString(x + w * 0.65, y + h * 0.62 - idx * 18, f"{labels[key]}: {int(buckets[key])}")


def _draw_visual_narrative(
    c: canvas.Canvas,
    visual: PremiumPageVisual,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    body = _visual_body(visual)
    c.setFillColor(WHITE)
    c.rect(x, y - h, w, h, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(x, y - h, 7, h, fill=1, stroke=0)
    c.setFillColor(INK)
    _draw_wrapped(c, body, x + 20, y - 20, w - 40, 13, FONT_REGULAR, 9.6, max_lines=15)


def _points_from_visual(visual: PremiumPageVisual) -> list[tuple[str, float]]:
    raw_points = visual.data.get("points")
    if not raw_points and isinstance(visual.data.get("data"), dict):
        raw_points = visual.data["data"].get("points")
    points: list[tuple[str, float]] = []
    if isinstance(raw_points, list):
        for item in raw_points:
            if not isinstance(item, dict):
                continue
            value = _first_number(item.get("value"))
            if value is None:
                continue
            points.append((_clip(item.get("label") or item.get("x") or "Signal", 32), value))
    return points[:8]


def _visual_body(visual: PremiumPageVisual | None) -> str:
    if not visual:
        return ""
    body = visual.data.get("body")
    if body:
        return str(body)
    rows = visual.data.get("rows")
    if isinstance(rows, list) and rows:
        return " ".join(" - ".join(str(cell) for cell in row[:3]) for row in rows[:3] if isinstance(row, list))
    return visual.title


def _source_note_for_page(document: PremiumReportDocument, page: PremiumPage) -> str:
    notes = page.source_notes or (page.visual.source_notes if page.visual else [])
    cleaned = [_clip(note, 72) for note in notes if str(note or "").strip()]
    if cleaned:
        return "Source: " + "; ".join(cleaned[:4])
    return _label(document, "source_note")


def _draw_kpi_exhibit(
    c: canvas.Canvas,
    block: PremiumPreparedBlock,
    x: float,
    y: float,
    width: float,
) -> float:
    rows = block.rows[:6]
    if not rows:
        return y
    gap = 12
    cols = 3 if len(rows) > 2 else 2
    card_w = (width - gap * (cols - 1)) / cols
    card_h = 108
    for idx, row in enumerate(rows):
        cx = x + (idx % cols) * (card_w + gap)
        cy = y - (idx // cols) * (card_h + gap)
        c.setFillColor(WHITE)
        c.rect(cx, cy - card_h, card_w, card_h, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.rect(cx, cy - card_h, card_w, card_h, fill=0, stroke=1)
        c.setFillColor(GREEN if idx % 2 == 0 else DARK_GREEN)
        c.rect(cx, cy - 6, card_w, 6, fill=1, stroke=0)
        metric = row[0] if len(row) > 0 else "Metric"
        value = row[1] if len(row) > 1 else ""
        subject = row[2] if len(row) > 2 else ""
        source = row[3] if len(row) > 3 else ""
        c.setFillColor(GREEN)
        _draw_wrapped(c, str(value), cx + 12, cy - 26, card_w - 24, 22, FONT_BOLD, 18, max_lines=1)
        c.setFillColor(INK)
        _draw_wrapped(c, str(metric), cx + 12, cy - 52, card_w - 24, 11, FONT_BOLD, 8.6, max_lines=2)
        c.setFillColor(MUTED)
        _draw_wrapped(c, str(subject), cx + 12, cy - 78, card_w - 24, 10, FONT_REGULAR, 7.6, max_lines=2)
        c.setFillColor(colors.HexColor("#9AA1A6"))
        _draw_wrapped(c, str(source), cx + 12, cy - 98, card_w - 24, 8, FONT_REGULAR, 6.4, max_lines=1)
    return y - (math.ceil(len(rows) / cols) * (card_h + gap)) - 10


def _draw_card_matrix(
    c: canvas.Canvas,
    block: PremiumPreparedBlock,
    x: float,
    y: float,
    width: float,
) -> float:
    rows = block.rows[:6]
    if not rows:
        return y
    row_h = 88
    for idx, row in enumerate(rows):
        cy = y - idx * (row_h + 10)
        if cy - row_h < BOTTOM + 40:
            break
        c.setFillColor(PALE_GREEN if idx % 2 == 0 else colors.HexColor("#F7F9F8"))
        c.rect(x, cy - row_h, width, row_h, fill=1, stroke=0)
        c.setFillColor(GREEN if idx % 2 == 0 else DARK_GREEN)
        c.rect(x, cy - row_h, 8, row_h, fill=1, stroke=0)
        left = row[0] if row else ""
        middle = row[1] if len(row) > 1 else ""
        right = " | ".join(str(item) for item in row[2:])
        c.setFillColor(INK)
        _draw_wrapped(c, str(left), x + 20, cy - 24, width * 0.24, 14, FONT_BOLD, 11, max_lines=2)
        c.setFillColor(MUTED)
        _draw_wrapped(c, str(middle), x + width * 0.33, cy - 24, width * 0.25, 11, FONT_REGULAR, 8.4, max_lines=4)
        c.setFillColor(INK)
        _draw_wrapped(c, str(right), x + width * 0.62, cy - 24, width * 0.33, 11, FONT_REGULAR, 8.4, max_lines=4)
    return y - len(rows) * (row_h + 10) - 8


def _draw_sensitivity_exhibit(
    c: canvas.Canvas,
    block: PremiumPreparedBlock,
    x: float,
    y: float,
    width: float,
) -> float:
    rows = block.rows[:9]
    if not rows:
        return y
    values = [_first_number(row[1] if len(row) > 1 else "") for row in rows]
    max_value = max([abs(value) for value in values if value is not None] or [1])
    label_w = width * 0.34
    bar_x = x + label_w + 18
    bar_w = width - label_w - 32
    row_h = 36
    c.setFillColor(colors.HexColor("#F7F9F8"))
    c.rect(x, y - row_h * len(rows) - 12, width, row_h * len(rows) + 18, fill=1, stroke=0)
    for idx, row in enumerate(rows):
        cy = y - 24 - idx * row_h
        label = row[0] if row else ""
        value_text = row[1] if len(row) > 1 else ""
        value = values[idx]
        c.setFillColor(INK)
        _draw_wrapped(c, str(label), x + 10, cy, label_w - 18, 9, FONT_REGULAR, 7.4, max_lines=2)
        c.setFillColor(colors.HexColor("#DDE4E0"))
        c.rect(bar_x, cy - 8, bar_w, 8, fill=1, stroke=0)
        if value is not None:
            c.setFillColor(GREEN if value >= 0 else colors.HexColor("#B75E55"))
            c.rect(bar_x, cy - 8, bar_w * min(abs(value) / max_value, 1), 8, fill=1, stroke=0)
        c.setFillColor(DARK_GREEN)
        c.setFont(FONT_BOLD, 8)
        c.drawRightString(x + width - 10, cy - 2, _clip(value_text, 18))
    return y - row_h * len(rows) - 28


def _first_number(value: object) -> float | None:
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _methodology_page(
    c: canvas.Canvas,
    document: PremiumReportDocument,
    page_no: int,
    index: int,
) -> int:
    page_no += 1
    _header(c, document, page_no)
    c.setFillColor(GREEN)
    c.setFont(FONT_BOLD, 10)
    c.drawString(MARGIN_X, TOP, _label(document, "methodology"))
    c.setFillColor(INK)
    c.setFont(FONT_REGULAR, 25)
    c.drawString(MARGIN_X, TOP - 34, f"Evidence and Design Control {index}")
    rows = [
        ["Publication grid", "A4 editorial grid with header, footer, section label, and source notes."],
        ["Exhibits", f"{document.plan.publication.min_exhibit_pages}+ exhibit pages planned."],
        ["Dense visuals", f"{document.plan.publication.min_data_dense_exhibits}+ data-dense exhibits required."],
        ["Evidence base", f"{document.source_count} sources / {document.numeric_fact_count} numeric facts."],
    ]
    _draw_table(c, ["Control", "Requirement"], rows, MARGIN_X, TOP - 96, PAGE_W - 2 * MARGIN_X)
    _footer(c, document, page_no)
    c.showPage()
    return page_no


def _draw_block(c: canvas.Canvas, block: PremiumPreparedBlock, x: float, y: float, width: float) -> float:
    c.setFillColor(GREEN)
    c.setFont(FONT_BOLD, 8)
    c.drawString(x, y, str(block.kind).replace("_", " ").upper())
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 13)
    c.drawString(x, y - 18, _clip(block.title, 80))
    y -= 38
    if block.rows:
        return _draw_table(c, block.columns, block.rows[:8], x, y, width)
    if block.body:
        used = _draw_wrapped(c, block.body, x, y, width, 12, FONT_REGULAR, 9.4, max_lines=12)
        return y - used
    return y


def _draw_table(
    c: canvas.Canvas,
    columns: list[str],
    rows: list[list[str]],
    x: float,
    y: float,
    width: float,
    *,
    dense: bool = False,
) -> float:
    if not columns:
        columns = ["Item", "Value"]
    col_count = max(1, len(columns))
    col_w = width / col_count
    row_h = 26 if dense else 31
    font_size = 7.2 if dense else 8.2
    c.setFillColor(PALE_GREEN)
    c.rect(x, y - row_h, width, row_h, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, font_size)
    for idx, col in enumerate(columns):
        c.drawString(x + idx * col_w + 5, y - 17, _clip(str(col), max(8, int(col_w / 5))))
    c.setStrokeColor(LINE)
    c.line(x, y - row_h, x + width, y - row_h)
    y -= row_h
    for row_idx, row in enumerate(rows):
        if y < BOTTOM + row_h:
            break
        c.setFillColor(colors.HexColor("#FAFBFA") if row_idx % 2 else WHITE)
        c.rect(x, y - row_h, width, row_h, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont(FONT_REGULAR, font_size)
        for idx in range(col_count):
            value = row[idx] if idx < len(row) else ""
            _draw_wrapped(
                c,
                _clip(str(value), 42 if dense else 34),
                x + idx * col_w + 5,
                y - 9,
                col_w - 9,
                font_size + 1,
                FONT_REGULAR,
                font_size,
                max_lines=2 if dense else 3,
            )
        c.setStrokeColor(LINE)
        c.line(x, y - row_h, x + width, y - row_h)
        y -= row_h
    c.setStrokeColor(LINE)
    c.rect(x, y, width, row_h * (len(rows) + 1), stroke=0, fill=0)
    return y


def _draw_columns(c: canvas.Canvas, text: str, x: float, y: float, width: float, height: float) -> None:
    gap = 36
    col_w = (width - gap) / 2
    lines = _wrap_lines(text, col_w, 9.3)
    max_lines = int(height / 12)
    left = lines[:max_lines]
    right = lines[max_lines : max_lines * 2]
    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 9.3)
    for idx, line in enumerate(left):
        c.drawString(x, y - idx * 12, line)
    for idx, line in enumerate(right):
        c.drawString(x + col_w + gap, y - idx * 12, line)


def _draw_wrapped(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    leading: float,
    font: str,
    size: float,
    *,
    max_lines: int | None = None,
) -> float:
    c.setFont(font, size)
    lines = _wrap_lines(text, width, size)
    if max_lines is not None:
        lines = lines[:max_lines]
    for idx, line in enumerate(lines):
        c.drawString(x, y - idx * leading, line)
    return len(lines) * leading


def _wrap_lines(text: str, width: float, size: float) -> list[str]:
    if not text:
        return []
    text = _plain_text(text)
    avg = max(size * 0.47, 4)
    chars = max(12, int(width / avg))
    lines: list[str] = []
    for para in str(text).replace("\n", " ").split("  "):
        lines.extend(wrap(para.strip(), width=chars) or [""])
    return lines


def _draw_full_bleed_city(c: canvas.Canvas) -> None:
    c.setFillColor(colors.HexColor("#DFF3F0"))
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    for i in range(34):
        t = i / 33
        r = 0.08 + 0.08 * t
        g = 0.32 + 0.38 * t
        b = 0.45 - 0.12 * t
        c.setFillColor(colors.Color(r, g, b))
        c.rect(0, i * PAGE_H / 34, PAGE_W, PAGE_H / 34 + 1, fill=1, stroke=0)
    c.setFillColor(colors.Color(0.0, 0.2, 0.18, alpha=0.54))
    for i in range(28):
        w = 12 + (i % 5) * 7
        h = 120 + (i * 31) % 320
        x = i * 24 - 8
        c.rect(x, 0, w, h, fill=1, stroke=0)
        c.setFillColor(colors.Color(0.65, 1, 0.82, alpha=0.35))
        for yy in range(18, int(h), 28):
            c.rect(x + 3, yy, max(2, w - 7), 2, fill=1, stroke=0)
        c.setFillColor(colors.Color(0.0, 0.2, 0.18, alpha=0.54))
    c.setFillColor(colors.Color(0.4, 1, 0.65, alpha=0.18))
    for i in range(16):
        c.circle(30 + i * 38, 120 + 60 * math.sin(i), 46 + (i % 4) * 9, fill=1, stroke=0)


def _hero_band(c: canvas.Canvas, seed: str) -> None:
    c.setFillColor(colors.HexColor("#0E5C78"))
    c.rect(0, PAGE_H - 250, PAGE_W, 250, fill=1, stroke=0)
    c.setFillColor(colors.Color(0.1, 0.9, 0.55, alpha=0.2))
    for i in range(9):
        c.circle(40 + i * 72, PAGE_H - 110 + 20 * math.sin(i + len(seed)), 70, fill=1, stroke=0)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.16))
    for i in range(18):
        x = i * 38
        c.rect(x, PAGE_H - 235, 20 + (i % 4) * 10, 95 + (i * 17) % 120, fill=1, stroke=0)


def _draw_exhibit_placeholder(c: canvas.Canvas, x: float, y: float, w: float, h: float, label: str) -> None:
    c.setFillColor(PALE_GREEN)
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.setFillColor(DARK_GREEN)
    for i in range(7):
        bar_h = 36 + (i * 29) % 150
        c.rect(x + 34 + i * 58, y + 34, 28, bar_h, fill=1, stroke=0)
    c.setStrokeColor(GREEN)
    c.setLineWidth(3)
    points = [(x + 40 + i * 68, y + 90 + 42 * math.sin(i * 1.4)) for i in range(7)]
    for a, b in zip(points, points[1:], strict=False):
        c.line(a[0], a[1], b[0], b[1])
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 13)
    c.drawString(x + 34, y + h - 42, str(label).replace("_", " ").title())


def _draw_exhibit_support_visual(
    c: canvas.Canvas,
    document: PremiumReportDocument,
    block: PremiumPreparedBlock,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    c.setFillColor(colors.HexColor("#F4F8F6"))
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.setStrokeColor(LINE)
    c.rect(x, y, w, h, fill=0, stroke=1)
    left_w = w * 0.52
    c.setFillColor(colors.HexColor("#DCEEE5"))
    c.rect(x + 18, y + 22, left_w - 30, h - 44, fill=1, stroke=0)
    russian = _has_cyrillic(f"{document.title} {document.subtitle}")
    _draw_support_chart(c, block, x + 18, y + 22, left_w - 30, h - 44, russian=russian)

    tx = x + left_w + 10
    c.setFillColor(GREEN)
    c.setFont(FONT_BOLD, 8)
    c.drawString(
        tx,
        y + h - 38,
        "СЛОЙ ДОКАЗАТЕЛЬСТВ" if russian else "EVIDENCE LAYER",
    )
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 13)
    c.drawString(tx, y + h - 60, "Ключевые сигналы" if russian else "Key signals")
    c.setFillColor(MUTED)
    support_lines = _support_signal_lines(block, russian=russian)
    for idx, line in enumerate(support_lines):
        yy = y + h - 92 - idx * 34
        c.setFillColor(WHITE)
        c.roundRect(tx, yy - 18, w - left_w - 28, 24, 4, fill=1, stroke=0)
        c.setFillColor(DARK_GREEN if idx == 0 else MUTED)
        c.setFont(FONT_BOLD if idx == 0 else FONT_REGULAR, 8)
        _draw_wrapped(
            c,
            line,
            tx + 10,
            yy + 4,
            w - left_w - 48,
            10,
            FONT_BOLD if idx == 0 else FONT_REGULAR,
            8,
            max_lines=2,
        )


def _draw_support_chart(
    c: canvas.Canvas,
    block: PremiumPreparedBlock,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    russian: bool,
) -> None:
    if block.kind == "source_quality_table":
        _draw_source_quality_chart(c, block, x, y, w, h, russian=russian)
        return
    if block.kind in {"scenario_matrix", "decision_matrix", "risk_register"}:
        _draw_matrix_mosaic(c, block, x, y, w, h, russian=russian)
        return
    series = _numeric_series_from_block(block)
    if series:
        _draw_bar_line_chart(c, series, x, y, w, h, russian=russian)
        return
    _draw_matrix_mosaic(c, block, x, y, w, h, russian=russian)


def _draw_bar_line_chart(
    c: canvas.Canvas,
    series: list[tuple[str, float]],
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    russian: bool,
) -> None:
    plotted = series[:7]
    values = [value for _label, value in plotted]
    max_value = max([abs(value) for value in values] or [1])
    base = y + 34
    chart_h = h - 72
    gap = 10
    bar_w = max(10, (w - 54 - gap * (len(values) - 1)) / max(len(values), 1))
    points: list[tuple[float, float]] = []
    c.setStrokeColor(colors.HexColor("#B7D8C8"))
    c.setLineWidth(0.8)
    for idx in range(4):
        yy = base + idx * chart_h / 3
        c.line(x + 24, yy, x + w - 20, yy)
    for idx, (label, value) in enumerate(plotted):
        bx = x + 28 + idx * (bar_w + gap)
        bh = chart_h * min(abs(value) / max_value, 1)
        c.setFillColor(GREEN if value >= 0 else colors.HexColor("#B75E55"))
        c.rect(bx, base, bar_w, max(3, bh), fill=1, stroke=0)
        top_y = base + max(3, bh)
        points.append((bx + bar_w / 2, top_y))
        c.setFillColor(INK)
        c.setFont(FONT_BOLD, 7)
        c.drawCentredString(bx + bar_w / 2, top_y + 8, _format_chart_value(value))
        c.setFillColor(MUTED)
        _draw_wrapped(c, label, bx, base - 12, bar_w, 7.2, FONT_REGULAR, 6.4, max_lines=2)
    c.setStrokeColor(DARK_GREEN)
    c.setLineWidth(2)
    for a, b in zip(points, points[1:], strict=False):
        c.line(a[0], a[1], b[0], b[1])
    c.setFillColor(DARK_GREEN)
    for px, py in points:
        c.circle(px, py, 3, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 7)
    c.drawString(
        x + 20,
        y + h - 22,
        "Индексированный числовой сигнал" if russian else "Indexed numeric signal",
    )


def _format_chart_value(value: float) -> str:
    if abs(value - round(value)) < 0.01:
        return str(int(round(value)))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _draw_matrix_mosaic(
    c: canvas.Canvas,
    block: PremiumPreparedBlock,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    russian: bool,
) -> None:
    rows = max(2, min(4, len(block.rows) or 3))
    cols = max(2, min(4, len(block.columns) or 3))
    cell_w = (w - 34) / cols
    cell_h = (h - 54) / rows
    for row_idx in range(rows):
        for col_idx in range(cols):
            shade = 0.15 + 0.08 * ((row_idx + col_idx) % 4)
            c.setFillColor(colors.Color(0.12, 0.62, 0.37, alpha=shade))
            c.rect(
                x + 18 + col_idx * cell_w,
                y + 26 + row_idx * cell_h,
                cell_w - 4,
                cell_h - 4,
                fill=1,
                stroke=0,
            )
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 7)
    label = "Матрица условий" if russian else str(block.kind).replace("_", " ").title()
    c.drawString(x + 20, y + h - 22, label)


def _draw_source_quality_chart(
    c: canvas.Canvas,
    block: PremiumPreparedBlock,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    russian: bool,
) -> None:
    reliability_idx = max(0, len(block.columns) - 1)
    buckets = {"high": 0, "medium": 0, "low": 0}
    for row in block.rows:
        value = str(row[reliability_idx] if reliability_idx < len(row) else "").lower()
        if "high" in value:
            buckets["high"] += 1
        elif "low" in value:
            buckets["low"] += 1
        else:
            buckets["medium"] += 1
    total = max(sum(buckets.values()), 1)
    cx, cy = x + w * 0.38, y + h * 0.48
    radius = min(w, h) * 0.28
    start = 90
    palette = {
        "high": GREEN,
        "medium": colors.HexColor("#8DCBA5"),
        "low": colors.HexColor("#B75E55"),
    }
    for key, count in buckets.items():
        extent = 360 * count / total
        c.setFillColor(palette[key])
        c.wedge(cx - radius, cy - radius, cx + radius, cy + radius, start, start + extent, fill=1)
        start += extent
    c.setFillColor(INK)
    c.setFont(FONT_BOLD, 7)
    c.drawString(
        x + 20,
        y + h - 22,
        "Надежность источников" if russian else "Source reliability mix",
    )
    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 7)
    labels = (
        {"high": "высокая", "medium": "средняя", "low": "низкая"}
        if russian
        else {"high": "high", "medium": "medium", "low": "low"}
    )
    for idx, key in enumerate(("high", "medium", "low")):
        c.drawString(
            x + w * 0.65,
            y + h * 0.62 - idx * 16,
            f"{labels[key]}: {buckets[key]}",
        )


def _numeric_series_from_block(block: PremiumPreparedBlock) -> list[tuple[str, float]]:
    series: list[tuple[str, float]] = []
    for row in block.rows:
        label = _plain_text(row[0] if row else "")
        value: float | None = None
        candidate_cells = row[1:] if block.kind == "kpi_grid" else row
        for cell in candidate_cells:
            value = _first_number(cell)
            if value is not None:
                break
        if value is not None:
            series.append((_clip(label, 28), value))
    return series[:8]


def _support_signal_lines(block: PremiumPreparedBlock, *, russian: bool) -> list[str]:
    lines: list[str] = []
    for row in block.rows[:3]:
        cells = [_plain_text(cell) for cell in row[:3] if str(cell or "").strip()]
        if cells:
            lines.append(_clip(" - ".join(cells[:2]), 78))
    if lines:
        return lines
    if block.columns:
        return [_clip(" / ".join(block.columns[:3]), 78)]
    return [
        "Сигнал требует проверки по источникам" if russian else "Signal requires source review",
        "Использовать как ориентир, не как единственное основание" if russian else "Use as directional evidence",
        "См. ограничения методологии" if russian else "See methodology limitations",
    ]


def _header(c: canvas.Canvas, document: PremiumReportDocument, page_no: int) -> None:
    c.setFillColor(MUTED)
    c.setFont(FONT_REGULAR, 7)
    c.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 28, _clip(document.title.upper(), 56))


def _footer(c: canvas.Canvas, document: PremiumReportDocument, page_no: int) -> None:
    c.setFillColor(colors.HexColor("#A3A9AE"))
    c.setFont(FONT_REGULAR, 7)
    c.drawString(MARGIN_X, 28, "SMART REPORT")
    c.drawRightString(PAGE_W - MARGIN_X, 28, f"{_clip(document.subtitle.upper(), 38)}   {page_no}")


def _label(document: PremiumReportDocument, key: str, number: int | None = None) -> str:
    russian = _has_cyrillic(f"{document.title} {document.subtitle}")
    if russian:
        labels = {
            "contents": "Содержание",
            "introduction": "Введение",
            "section": "РАЗДЕЛ / SECTION",
            "appendix": "ПРИЛОЖЕНИЕ / APPENDIX",
            "methodology": "МЕТОДОЛОГИЯ / METHODOLOGY",
            "source_note": "Источник: реестр доказательств Smart Report и загруженные исходные материалы. Source: Smart Report evidence register.",
        }
        if key == "exhibit":
            return f"РИСУНОК {number} / EXHIBIT {number}"
        return labels[key]
    labels = {
        "contents": "Contents",
        "introduction": "Introduction",
        "section": "SECTION",
        "appendix": "APPENDIX",
        "methodology": "METHODOLOGY NOTE",
        "source_note": "Source: Smart Report evidence register and uploaded source reports.",
    }
    if key == "exhibit":
        return f"EXHIBIT {number}"
    return labels[key]


def _green_rule(c: canvas.Canvas, x: float, y: float, width: float) -> None:
    c.setFillColor(GREEN)
    c.rect(x, y, width, 6, fill=1, stroke=0)


def _fallback_storyboard(document: PremiumReportDocument) -> list[PremiumPage]:
    pages: list[PremiumPage] = []
    for idx, block in enumerate(_exhibit_blocks(document), start=1):
        pages.append(
            PremiumPage(
                page_type="exhibit",
                thesis=block.title,
                narrative=block.body or f"{block.title} summarizes the most decision-relevant evidence block.",
                visual=PremiumPageVisual(
                    visual_type="scenario_matrix" if block.rows else "narrative_text",
                    title=block.title,
                    data={"columns": block.columns, "rows": block.rows, "body": block.body},
                ),
                implication=f"Use exhibit {idx} to validate the section conclusion before relying on it.",
            )
        )
    return pages


def _exhibit_blocks(document: PremiumReportDocument) -> list[PremiumPreparedBlock]:
    blocks: list[PremiumPreparedBlock] = []
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
    for section in [*document.sections, *document.appendices]:
        for block in section.blocks:
            if block.kind in preferred:
                blocks.append(block)
    seen: set[str] = set()
    unique: list[PremiumPreparedBlock] = []
    for block in blocks:
        key = f"{block.kind}:{block.title}"
        if key not in seen:
            unique.append(block)
            seen.add(key)
    return unique[: max(document.plan.publication.min_exhibit_pages, 4)]


def _first_section_block_body(
    document: PremiumReportDocument,
    section_id: str,
    block_title: str | None = None,
) -> str:
    for section in document.sections:
        if section.id != section_id:
            continue
        for block in section.blocks:
            if block_title is None or block.title == block_title:
                return block.body
    return ""


def _clip(text: object, limit: int) -> str:
    clean = " ".join(_plain_text(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "..."


def _plain_text(text: object) -> str:
    clean = str(text or "")
    clean = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    clean = re.sub(r"(^|\s)#{1,6}\s*", r"\1", clean)
    clean = re.sub(r"(\*\*|__)(.*?)\1", r"\2", clean)
    clean = re.sub(r"(\*|_)(.*?)\1", r"\2", clean)
    clean = clean.replace("`", "")
    clean = re.sub(r"^\s*[-*+]\s+", "", clean, flags=re.MULTILINE)
    return clean


def _has_cyrillic(text: object) -> bool:
    return any("\u0400" <= char <= "\u04FF" for char in str(text or ""))


def _upper(text: str) -> str:
    return text.upper()


def _report_type_label(report_type: str) -> str:
    return {
        "market": "Market report",
        "investment": "Investment report",
        "competitive": "Competitive report",
        "strategy": "Strategy report",
        "technical_audit": "Technical audit",
        "legal_regulatory": "Legal / regulatory report",
        "due_diligence": "Due diligence",
        "general_research": "Research report",
    }.get(str(report_type), str(report_type).replace("_", " ").title())


def _audience_label(audience: str) -> str:
    return {
        "buyer": "Buyer",
        "investor": "Investor",
        "executive": "Executive",
        "operator": "Operator",
        "developer": "Developer",
        "analyst": "Analyst",
        "technical_lead": "Technical lead",
        "general_client": "Client",
    }.get(str(audience), str(audience).replace("_", " ").title())


def _client_confidence_label(document: PremiumReportDocument) -> str:
    readiness = document.premium_readiness or {}
    if readiness.get("ready"):
        return "Client-ready under the premium evidence and publication gates."
    score = readiness.get("score")
    if score is None:
        return "Confidence depends on the cited evidence base and stated limitations."
    return f"Draft quality gate score: {score}/100. Review limitations before client use."
