"""One-page business-style HTML export. Print-to-PDF ready.

Dense single-A4 layout: title strip, executive summary, key numbers,
priority matrix, top cross-domain connections, next-step gaps.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from models import Report


NAVY = "#1B3A5C"
BLUE = "#2563EB"
AMBER = "#D97706"
RED = "#DC2626"
INK = "#0F172A"
MUTED = "#64748B"
SOFT = "#F1F5F9"
LINE = "#E2E8F0"

CSS = f"""
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; color: {INK};
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  background: #F8FAFC; }}
.page {{ width: 210mm; min-height: 297mm; margin: 0 auto; padding: 14mm 15mm;
  background: #fff; box-shadow: 0 4px 24px rgba(15,23,42,.08); }}
.strip {{ background: {NAVY}; color: #fff; padding: 10mm 12mm; margin: -14mm -15mm 6mm;
  display: flex; justify-content: space-between; align-items: flex-end; gap: 8mm; }}
.strip h1 {{ margin: 0; font-size: 18pt; font-weight: 600; line-height: 1.25;
  letter-spacing: -.01em; flex: 1; }}
.strip .meta {{ font-size: 8pt; opacity: .8; text-align: right; white-space: nowrap; }}
.strip .kicker {{ font-size: 8pt; font-weight: 600; letter-spacing: .12em;
  text-transform: uppercase; opacity: .75; margin-bottom: 2mm; }}
section {{ margin: 5mm 0; }}
h2 {{ font-size: 10pt; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; color: {NAVY}; margin: 0 0 2.5mm;
  border-bottom: 1.5pt solid {NAVY}; padding-bottom: 1mm; }}
p, li {{ font-size: 9.5pt; line-height: 1.5; margin: 0 0 2mm; }}
.summary {{ font-size: 10pt; line-height: 1.55; color: {INK}; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; }}
.grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; }}
.kpi {{ border-left: 3pt solid {BLUE}; padding: 2mm 3mm; background: {SOFT};
  border-radius: 0 2pt 2pt 0; }}
.kpi .n {{ font-size: 15pt; font-weight: 700; color: {NAVY}; line-height: 1.1; }}
.kpi .c {{ font-size: 8.5pt; color: {MUTED}; margin-top: 1mm; }}
.finding {{ display: flex; gap: 3mm; margin-bottom: 2.5mm; }}
.finding .num {{ width: 7mm; height: 7mm; flex: 0 0 auto; border-radius: 50%;
  background: {NAVY}; color: #fff; display: flex; align-items: center;
  justify-content: center; font-weight: 700; font-size: 9pt; }}
.finding .body {{ flex: 1; font-size: 9.5pt; line-height: 1.45; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9pt; }}
th, td {{ border-bottom: .5pt solid {LINE}; padding: 2mm 2mm;
  vertical-align: top; text-align: left; }}
th {{ background: {SOFT}; color: {NAVY}; font-weight: 600;
  font-size: 8pt; text-transform: uppercase; letter-spacing: .06em; }}
.pri-high {{ color: {RED}; font-weight: 600; }}
.pri-med {{ color: {AMBER}; font-weight: 600; }}
.pri-low {{ color: {MUTED}; }}
.conn {{ border-left: 3pt solid {BLUE}; padding: 1.5mm 3mm;
  margin-bottom: 2mm; background: {SOFT}; border-radius: 0 2pt 2pt 0; }}
.conn .pair {{ font-weight: 600; color: {NAVY}; font-size: 9pt; }}
.conn .desc {{ font-size: 8.5pt; color: {INK}; margin-top: .5mm; line-height: 1.4; }}
.gap {{ font-size: 9pt; padding-left: 4mm; position: relative; margin-bottom: 1.5mm; }}
.gap::before {{ content: "→"; position: absolute; left: 0; color: {BLUE}; font-weight: 700; }}
footer {{ margin-top: 6mm; padding-top: 3mm; border-top: .5pt solid {LINE};
  font-size: 7.5pt; color: {MUTED}; display: flex; justify-content: space-between; }}
@media print {{
  html, body {{ background: #fff; }}
  .page {{ box-shadow: none; margin: 0; }}
  @page {{ size: A4; margin: 0; }}
}}
"""


def _nature_icon(nature: str) -> str:
    return {
        "paradox": "⚡",
        "causal_chain": "→",
        "unexpected_confirmation": "✓",
        "shared_variable": "◇",
    }.get(nature, "◇")


def _priority_class(p: str) -> str:
    return {"high": "pri-high", "medium": "pri-med"}.get(p, "pri-low")


def _priority_label(p: str) -> str:
    return {"high": "Высокий", "medium": "Средний", "low": "Низкий"}.get(p, p or "—")


def _render_html(report: Report) -> str:
    import datetime as _dt

    goal = escape(report.goal or "Отчёт")
    today = _dt.date.today().strftime("%d.%m.%Y")

    # Top findings (prefer exec_summary top_findings, else quantitative findings)
    top_findings: list[str] = []
    if report.exec_summary and report.exec_summary.top_findings:
        top_findings = [tf.headline for tf in report.exec_summary.top_findings[:3]]
    if not top_findings:
        for b in report.blocks:
            for f in (b.findings or []):
                if f.has_numbers and f.claim:
                    top_findings.append(f.claim)
                if len(top_findings) >= 3:
                    break
            if len(top_findings) >= 3:
                break

    # KPIs: pick up to 3 quantitative findings distinct from top_findings
    kpis: list[tuple[str, str]] = []
    seen = {t.strip()[:80] for t in top_findings}
    for b in report.blocks:
        for f in (b.findings or []):
            if not f.has_numbers:
                continue
            key = (f.claim or "").strip()[:80]
            if not key or key in seen:
                continue
            seen.add(key)
            # Extract first numeric token as the KPI "number"
            import re
            m = re.search(r"([\d][\d\s.,]*%?|\$\s?[\d.,]+[kmbтмлрд]*)", f.claim)
            number = m.group(1).strip() if m else "—"
            context = f.claim
            if len(context) > 90:
                context = context[:87] + "…"
            kpis.append((number, context))
            if len(kpis) >= 3:
                break
        if len(kpis) >= 3:
            break

    # Priority rows from block_headers
    header_by_cell = {h.cell: h for h in (report.block_headers or [])}
    rows: list[tuple[str, str, str, str]] = []
    ordered = sorted(
        report.blocks,
        key=lambda b: {"high": 0, "medium": 1, "low": 2}.get(
            (header_by_cell.get(b.cell).priority if header_by_cell.get(b.cell) else "low"), 3
        ),
    )
    for b in ordered[:6]:
        h = header_by_cell.get(b.cell)
        pri = h.priority if h else "low"
        one = h.one_liner if h and h.one_liner else (b.summary or "")[:140]
        num = h.strongest_number if h and h.strongest_number else ""
        rows.append((b.cell, one, num, pri))

    # Connections
    conns = (report.connections or [])[:3]

    # Gaps
    gaps: list[str] = []
    if report.exec_summary and report.exec_summary.key_gaps:
        gaps = report.exec_summary.key_gaps[:4]
    if not gaps:
        for b in report.blocks:
            if b.gaps:
                gaps.append(b.gaps[0])
            if len(gaps) >= 4:
                break

    # Summary lead
    lead = ""
    if report.exec_summary and report.exec_summary.goal_restate:
        lead = report.exec_summary.goal_restate

    parts: list[str] = []
    parts.append(f"<!doctype html><html lang='ru'><head><meta charset='utf-8'>")
    parts.append(f"<title>{goal}</title><style>{CSS}</style></head><body>")
    parts.append("<div class='page'>")
    parts.append(
        f"<div class='strip'><div>"
        f"<div class='kicker'>One-pager · Smart Report</div>"
        f"<h1>{goal}</h1></div>"
        f"<div class='meta'>{today}<br>{len(report.blocks)} блоков · "
        f"{len(report.connections)} связей</div></div>"
    )

    if lead:
        parts.append(f"<section class='summary'>{escape(lead)}</section>")

    if top_findings:
        parts.append("<section><h2>Главные выводы</h2>")
        for i, tf in enumerate(top_findings, 1):
            parts.append(
                f"<div class='finding'><div class='num'>{i}</div>"
                f"<div class='body'>{escape(tf)}</div></div>"
            )
        parts.append("</section>")

    if kpis:
        parts.append("<section><h2>Ключевые цифры</h2><div class='grid-3'>")
        for num, ctx in kpis:
            parts.append(
                f"<div class='kpi'><div class='n'>{escape(num)}</div>"
                f"<div class='c'>{escape(ctx)}</div></div>"
            )
        parts.append("</div></section>")

    if rows:
        parts.append(
            "<section><h2>Приоритеты по блокам</h2>"
            "<table><thead><tr><th style='width:28%'>Ячейка</th>"
            "<th>Суть</th><th style='width:14%'>Цифра</th>"
            "<th style='width:14%'>Приоритет</th></tr></thead><tbody>"
        )
        for cell, one, num, pri in rows:
            parts.append(
                f"<tr><td>{escape(cell)}</td><td>{escape(one)}</td>"
                f"<td>{escape(num or '—')}</td>"
                f"<td class='{_priority_class(pri)}'>{_priority_label(pri)}</td></tr>"
            )
        parts.append("</tbody></table></section>")

    if conns:
        parts.append("<section><h2>Неожиданные связи</h2>")
        for c in conns:
            icon = _nature_icon(c.nature)
            pair = " ↔ ".join(c.domains or [])
            parts.append(
                f"<div class='conn'><div class='pair'>{icon} {escape(pair)}</div>"
                f"<div class='desc'>{escape(c.description or '')}</div></div>"
            )
        parts.append("</section>")

    chains = list(getattr(report, "causal_chains", []) or [])
    if chains:
        parts.append("<section><h2>Длинные причинные цепочки</h2>")
        for ch in chains[:3]:
            dom = " · ".join(ch.domains or [])
            parts.append(
                f"<div class='conn'><div class='pair'>🔗 {escape(ch.title)}"
                f" <span style='color:{MUTED};font-weight:400'>({escape(dom)})</span></div>"
            )
            steps = " → ".join(
                escape(f"{l.cause} → {l.effect}") for l in (ch.links or [])[:5]
            )
            parts.append(f"<div class='desc'>{steps}</div>")
            if ch.terminal_implication:
                parts.append(
                    f"<div class='desc'><b>Итог:</b> {escape(ch.terminal_implication)}"
                    f" <span style='color:{MUTED}'>[{escape(ch.confidence)}]</span></div>"
                )
            parts.append("</div>")
        parts.append("</section>")

    pms = list(getattr(report, "pre_mortems", []) or [])
    if pms:
        parts.append("<section><h2>Pre-mortem: где вывод может провалиться</h2>")
        parts.append("<table><thead><tr><th>Режим провала</th><th>P</th><th>Ранний сигнал</th><th>Митигация</th></tr></thead><tbody>")
        for pm in pms[:6]:
            parts.append(
                f"<tr><td>{escape(pm.failure_mode)}</td>"
                f"<td>{escape(pm.probability)}</td>"
                f"<td>{escape(pm.early_signal)}</td>"
                f"<td>{escape(pm.mitigation)}</td></tr>"
            )
        parts.append("</tbody></table></section>")

    analogies = []
    indicators = []
    decision_points = []
    for b in report.blocks:
        for a in (getattr(b, "analogies", None) or []):
            analogies.append((b.cell, a))
        for iw in (getattr(b, "indicators", None) or []):
            indicators.append((b.cell, iw))
        dp = getattr(b, "decision_point", None)
        if dp:
            decision_points.append((b.cell, dp))

    if analogies:
        parts.append("<section><h2>Исторические аналогии</h2>")
        for cell, a in analogies[:4]:
            parts.append(
                f"<div class='conn'><div class='pair'>{escape(cell)}: {escape(a.situation)}</div>"
                f"<div class='desc'>Ожидалось: {escape(a.expected)}. Фактически: {escape(a.actual)}. "
                f"Почему разошлось: {escape(a.why_diverged)}. <b>Урок:</b> {escape(a.lesson)}</div></div>"
            )
        parts.append("</section>")

    if indicators:
        parts.append("<section><h2>Indicators & Warnings</h2>")
        parts.append("<table><thead><tr><th>Гипотеза</th><th>Сигнал</th><th>Где смотреть</th><th>Горизонт</th></tr></thead><tbody>")
        for cell, iw in indicators[:8]:
            parts.append(
                f"<tr><td>{escape(iw.hypothesis)}</td>"
                f"<td>{escape(iw.indicator)}</td>"
                f"<td>{escape(iw.where_to_look)}</td>"
                f"<td>{escape(iw.timeframe)}</td></tr>"
            )
        parts.append("</tbody></table></section>")

    if decision_points:
        parts.append("<section><h2>Ключевые развилки</h2>")
        for cell, dp in decision_points[:6]:
            parts.append(f"<div class='gap'><b>{escape(cell)}:</b> {escape(dp)}</div>")
        parts.append("</section>")

    if gaps:
        parts.append("<section><h2>Следующие шаги</h2>")
        for g in gaps:
            parts.append(f"<div class='gap'>{escape(g)}</div>")
        parts.append("</section>")

    parts.append(
        f"<footer><span>Smart Report · сгенерировано {today}</span>"
        f"<span>Для печати: Ctrl/Cmd + P → Save as PDF</span></footer>"
    )
    parts.append("</div></body></html>")
    return "".join(parts)


def export_onepager_html(report: Report, out_path: Path) -> Path:
    html = _render_html(report)
    out_path.write_text(html, encoding="utf-8")
    return out_path
