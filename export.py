"""Export Report → markdown / docx / json. Executive Summary first; blocks sorted by priority."""
from __future__ import annotations

import json
from pathlib import Path

from docx import Document

from models import BlockHeader, Report

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
PRIORITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}


def _headers_by_cell(report: Report) -> dict[str, BlockHeader]:
    return {h.cell: h for h in report.block_headers}


def _sorted_blocks(report: Report):
    headers = _headers_by_cell(report)

    def _key(block):
        h = headers.get(block.cell)
        prio = PRIORITY_ORDER.get(h.priority if h else "", 3)
        score = (
            -(h.score_novelty + h.score_concreteness + h.score_applicability) if h else 0
        )
        return (prio, score, block.cell)

    return sorted(report.blocks, key=_key)


# ---------- markdown ----------


def to_markdown(report: Report) -> str:
    lines: list[str] = ["# Аналитический отчёт\n", f"**Цель:** {report.goal}\n"]

    es = report.exec_summary
    if es is not None:
        lines.append("\n## Executive Summary\n")
        lines.append(f"**Цель:** {es.goal_restate}\n")
        lines.append("\n### Матрица доменов\n")
        lines.append(es.matrix_table_md.strip() + "\n")
        lines.append("\n### Топ-5 находок\n")
        for f in es.top_findings:
            lines.append(f"- **[{f.block_cell}]** {f.headline}")
        lines.append("\n### Топ-3 кросс-доменных связи\n")
        for c in es.top_connections:
            doms = " ↔ ".join(c.domains) if c.domains else ""
            lines.append(f"- **{doms}** — {c.headline}" if doms else f"- {c.headline}")
        lines.append("\n### Ключевые пробелы\n")
        for g in es.key_gaps:
            lines.append(f"- {g}")
        lines.append("\n---\n")

    lines.append("\n## Матрица доменов (развёрнуто)\n")
    for d in report.matrix.domains:
        lines.append(f"### {d.name}\n")
        lines.append(f"_{d.rationale}_\n")
        for layer in d.layers:
            lines.append(f"- **{layer.name}** — {layer.description}")
        lines.append("")

    lines.append("\n## Блоки (по приоритету)\n")
    headers = _headers_by_cell(report)
    for b in _sorted_blocks(report):
        h = headers.get(b.cell)
        emoji = PRIORITY_EMOJI.get(h.priority, "⚪") if h else "⚪"
        lines.append(f"### {emoji} {b.cell}\n")
        if h is not None:
            lines.append(f"- **Вывод:** {h.one_liner}")
            lines.append(f"- **Сильнейшая цифра:** {h.strongest_number}")
            lines.append(f"- **Главный пробел:** {h.main_gap}")
            lines.append(
                f"- **Оценка:** новизна {h.score_novelty}/3 · конкретность "
                f"{h.score_concreteness}/3 · применимость {h.score_applicability}/3 → "
                f"**{h.priority}**"
            )
            lines.append("")
        lines.append(b.summary.strip() + "\n")
        if b.findings:
            lines.append("**Источники:**\n")
            for f in b.findings:
                num = "📊 " if f.has_numbers else ""
                lines.append(f"- {num}{f.claim} — [{f.source_type}] {f.source}")
            lines.append("")
        if b.assumptions:
            lines.append("**Ключевые допущения (Key Assumptions Check):**\n")
            for a in b.assumptions:
                lines.append(f"- {a}")
            lines.append("")
        if b.gaps:
            lines.append("**Пробелы / куда копать дальше:**\n")
            for g in b.gaps:
                lines.append(f"- {g}")
            lines.append("")

    if report.connections:
        lines.append("\n## Кросс-доменные связи (бисоциация)\n")
        for c in report.connections:
            lines.append(
                f"### {' ↔ '.join(c.domains)} · {c.nature} · _{c.strength}_\n"
            )
            lines.append(f"**Общая переменная:** {c.shared_entity}\n")
            lines.append(c.description + "\n")
            if c.anchors:
                lines.append("**Опоры в блоках:**\n")
                for a in c.anchors:
                    lines.append(f"- {a}")
                lines.append("")
            if c.novelty:
                lines.append(f"**Что нового:** {c.novelty}\n")
    return "\n".join(lines)


# ---------- docx ----------


def to_docx(report: Report, path: Path) -> None:
    doc = Document()
    doc.add_heading("Аналитический отчёт", level=0)
    doc.add_paragraph(f"Цель: {report.goal}")

    es = report.exec_summary
    if es is not None:
        doc.add_heading("Executive Summary", level=1)
        doc.add_paragraph(es.goal_restate, style="Intense Quote")
        doc.add_heading("Матрица доменов", level=2)
        for line in es.matrix_table_md.splitlines():
            if line.strip():
                doc.add_paragraph(line)
        doc.add_heading("Топ-5 находок", level=2)
        for f in es.top_findings:
            doc.add_paragraph(f"[{f.block_cell}] {f.headline}", style="List Bullet")
        doc.add_heading("Топ-3 кросс-доменных связи", level=2)
        for c in es.top_connections:
            doms = " ↔ ".join(c.domains) if c.domains else ""
            text = f"{doms} — {c.headline}" if doms else c.headline
            doc.add_paragraph(text, style="List Bullet")
        doc.add_heading("Ключевые пробелы", level=2)
        for g in es.key_gaps:
            doc.add_paragraph(g, style="List Bullet")
        doc.add_page_break()

    doc.add_heading("Матрица доменов (развёрнуто)", level=1)
    for d in report.matrix.domains:
        doc.add_heading(d.name, level=2)
        doc.add_paragraph(d.rationale, style="Intense Quote")
        for layer in d.layers:
            doc.add_paragraph(f"{layer.name} — {layer.description}", style="List Bullet")

    doc.add_heading("Блоки (по приоритету)", level=1)
    headers = _headers_by_cell(report)
    for b in _sorted_blocks(report):
        h = headers.get(b.cell)
        emoji = PRIORITY_EMOJI.get(h.priority, "⚪") if h else "⚪"
        doc.add_heading(f"{emoji} {b.cell}", level=2)
        if h is not None:
            doc.add_paragraph(f"Вывод: {h.one_liner}")
            doc.add_paragraph(f"Сильнейшая цифра: {h.strongest_number}")
            doc.add_paragraph(f"Главный пробел: {h.main_gap}")
            doc.add_paragraph(
                f"Новизна {h.score_novelty}/3 · Конкретность {h.score_concreteness}/3 · "
                f"Применимость {h.score_applicability}/3 → {h.priority}"
            )
        for para in b.summary.split("\n\n"):
            if para.strip():
                doc.add_paragraph(para.strip())
        if b.findings:
            doc.add_heading("Источники", level=3)
            for f in b.findings:
                prefix = "📊 " if f.has_numbers else ""
                doc.add_paragraph(
                    f"{prefix}{f.claim} — [{f.source_type}] {f.source}", style="List Bullet"
                )
        if b.assumptions:
            doc.add_heading("Ключевые допущения", level=3)
            for a in b.assumptions:
                doc.add_paragraph(a, style="List Bullet")
        if b.gaps:
            doc.add_heading("Пробелы", level=3)
            for g in b.gaps:
                doc.add_paragraph(g, style="List Bullet")

    if report.connections:
        doc.add_heading("Кросс-доменные связи", level=1)
        for c in report.connections:
            doc.add_heading(
                f"{' ↔ '.join(c.domains)} · {c.nature} · {c.strength}", level=2
            )
            doc.add_paragraph(f"Общая переменная: {c.shared_entity}")
            doc.add_paragraph(c.description)
            if c.anchors:
                doc.add_heading("Опоры", level=3)
                for a in c.anchors:
                    doc.add_paragraph(a, style="List Bullet")
            if c.novelty:
                doc.add_paragraph(f"Что нового: {c.novelty}")

    doc.save(str(path))


# ---------- json + save_all ----------


def to_json(report: Report) -> str:
    return json.dumps(report.model_dump(), ensure_ascii=False, indent=2)


def save_all(report: Report, out_dir: Path, stem: str = "report") -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "md": out_dir / f"{stem}.md",
        "json": out_dir / f"{stem}.json",
        "docx": out_dir / f"{stem}.docx",
    }
    paths["md"].write_text(to_markdown(report), encoding="utf-8")
    paths["json"].write_text(to_json(report), encoding="utf-8")
    to_docx(report, paths["docx"])
    return paths
