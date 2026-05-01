"""Assemble a renderer-neutral premium report document.

The document assembler reuses the existing v4 analytical layer instead of
replacing it: executive answer, consensus, conflicts, gaps, numeric facts,
sources, bibliography, tables, charts, and metadata all flow into a richer
section/block structure. Renderers can target DOCX/PDF/PPTX later without
needing topic-specific logic.
"""

from __future__ import annotations

import re

from ...models import AnalysisOutput, FinalReport, NumericFact
from .models import (
    PremiumBlockKind,
    PremiumDeckSlideSpec,
    PremiumPage,
    PremiumPageVisual,
    PremiumPreparedBlock,
    PremiumPreparedSection,
    PremiumReportDocument,
    PremiumReportPlan,
    PremiumSectionSpec,
)
from .planner import build_premium_report_plan


def assemble_premium_report_document(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
    plan: PremiumReportPlan | None = None,
    premium_readiness: dict[str, object] | None = None,
) -> PremiumReportDocument:
    """Create a universal premium report/deck content model.

    This function is side-effect free and intentionally does not call legacy
    exporters. It prepares content that a future renderer can lay out with a
    premium visual system.
    """

    plan = plan or build_premium_report_plan(report, analysis=analysis)
    sections = [
        _section_from_spec(spec, report=report, analysis=analysis)
        for spec in plan.sections
        if spec.id != "appendix"
    ]
    appendices = _appendix_sections(report, analysis=analysis)
    deck_slides = _deck_slides(plan)
    numeric_facts = _numeric_facts(analysis)
    pages = _storyboard_pages(report, analysis=analysis, sections=sections, appendices=appendices)

    return PremiumReportDocument(
        title=_title_for(report),
        subtitle=_subtitle_for(plan),
        plan=plan,
        pages=pages,
        sections=sections,
        appendices=appendices,
        deck_slides=deck_slides,
        source_count=len(report.all_sources or []),
        numeric_fact_count=len(numeric_facts),
        premium_readiness=premium_readiness,
    )


def _storyboard_pages(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None,
    sections: list[PremiumPreparedSection],
    appendices: list[PremiumPreparedSection],
) -> list[PremiumPage]:
    """Build authored pages before any renderer lays them out.

    The block model is still useful as raw material, but consulting-style PDFs
    need a page thesis and a dominant visual per page.
    """

    pages: list[PremiumPage] = [
        PremiumPage(
            page_type="thesis",
            thesis=_executive_thesis(report),
            narrative=_compact_text(report.executive_summary.main_answer, 520),
            visual=_hero_kpi_visual(report, analysis),
            implication=_compact_text(report.executive_summary.confidence_note, 260),
            source_notes=_top_source_notes(report, analysis),
        )
    ]
    pages.extend(_chart_pages(report))
    pages.extend(_fact_driven_visual_pages(report, analysis))
    pages.extend(_decision_pages(report, sections))
    pages.extend(_narrative_pages(report))
    pages.extend(_appendix_pages(appendices))
    return _dedupe_pages(pages)


def _narrative_pages(report: FinalReport) -> list[PremiumPage]:
    pages: list[PremiumPage] = []
    for title, body in _main_synthesis_chapters(report.main_synthesis):
        pages.append(
            PremiumPage(
                page_type="thesis",
                thesis=title,
                narrative=_chapter_lead(body),
                visual=PremiumPageVisual(
                    visual_type="narrative_text",
                    title=title,
                    data={"body": body},
                ),
                implication=_chapter_implication(body),
                source_notes=[],
            )
        )
    for title, body in [
        ("Консенсус источников", report.consensus_section),
        ("Противоречия и как они разрешены", report.conflicts_section),
        ("Что закрыл добор и что осталось неизвестным", report.gaps_filled_section),
    ]:
        if body:
            pages.append(
                PremiumPage(
                    page_type="thesis",
                    thesis=title,
                    narrative=_chapter_lead(body),
                    visual=PremiumPageVisual(
                        visual_type="narrative_text",
                        title=title,
                        data={"body": body},
                    ),
                    implication=_chapter_implication(body),
                )
            )
    return pages[:7]


def _chapter_lead(body: str) -> str:
    text = " ".join(str(body or "").split())
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return _compact_text(" ".join(sentences[:2]), 360)


def _main_synthesis_chapters(markdown: str) -> list[tuple[str, str]]:
    text = str(markdown or "").strip()
    if not text:
        return []
    parts = re.split(r"\n(?=##\s+)", text)
    chapters: list[tuple[str, str]] = []
    for part in parts:
        clean = part.strip()
        if not clean:
            continue
        lines = clean.splitlines()
        first = lines[0].strip()
        if first.startswith("## "):
            title = first[3:].strip()
            body = "\n".join(lines[1:]).strip()
        else:
            title = "Ключевая логика вывода"
            body = clean
        if body:
            chapters.append((_compact_text(title, 120), body))
    return chapters[:4]


def _chapter_implication(body: str) -> str:
    text = " ".join(str(body or "").split())
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        if any(marker in sentence.lower() for marker in ["значит", "вывод", "для инвестора", "для покупателя", "это"]):
            return _compact_text(sentence, 320)
    return _compact_text(sentences[0], 320)


def _executive_thesis(report: FinalReport) -> str:
    answer = " ".join((report.executive_summary.main_answer or "").split())
    if not answer:
        return "Executive conclusion"
    sentence = re.split(r"(?<=[.!?])\s+", answer, maxsplit=1)[0]
    return _compact_text(sentence, 120)


def _hero_kpi_visual(report: FinalReport, analysis: AnalysisOutput | None) -> PremiumPageVisual:
    items = []
    for number in report.key_numbers_highlight[:6]:
        items.append(
            {
                "value": number.value,
                "label": number.label,
                "source": number.source_ref,
                "importance": number.importance,
            }
        )
    if len(items) < 6:
        for number in report.executive_summary.key_numbers[: 6 - len(items)]:
            items.append(
                {
                    "value": number.value,
                    "label": number.metric,
                    "source": number.source_url,
                    "importance": "primary",
                }
            )
    if len(items) < 6 and analysis is not None:
        for fact in _numeric_facts(analysis)[: 6 - len(items)]:
            items.append(
                {
                    "value": fact.value,
                    "label": f"{fact.metric}: {fact.subject}",
                    "source": _first_fact_source(fact),
                    "importance": "primary",
                }
            )
    return PremiumPageVisual(
        visual_type="hero_kpi_strip",
        title="Executive KPI strip",
        data={"items": items},
        source_notes=[item["source"] for item in items if item.get("source")],
    )


def _chart_pages(report: FinalReport) -> list[PremiumPage]:
    pages: list[PremiumPage] = []
    for chart in report.charts[:6]:
        visual_type = {
            "bar": "ranking_bar",
            "line": "time_series",
            "pie": "distribution",
            "scatter": "distribution",
            "stacked_bar": "distribution",
            "waterfall": "waterfall",
        }.get(chart.chart_type, "distribution")
        pages.append(
            PremiumPage(
                page_type="exhibit",
                thesis=chart.title,
                narrative=chart.caption or "Structured chart generated from the report evidence base.",
                visual=PremiumPageVisual(
                    visual_type=visual_type,  # type: ignore[arg-type]
                    title=chart.title,
                    data={
                        "chart_type": chart.chart_type,
                        "title": chart.title,
                        "data": chart.data,
                        "x_label": chart.x_label,
                        "y_label": chart.y_label,
                    },
                    source_notes=[chart.caption] if chart.caption else [],
                ),
                implication=chart.caption or "Use this exhibit to compare direction, scale, or relative position.",
                source_notes=[chart.caption] if chart.caption else [],
            )
        )
    return pages


def _fact_driven_visual_pages(
    report: FinalReport,
    analysis: AnalysisOutput | None,
) -> list[PremiumPage]:
    facts = _numeric_facts(analysis)
    pages: list[PremiumPage] = []
    series = _numeric_series_from_facts(facts)
    if len(series) >= 2:
        pages.append(
            PremiumPage(
                page_type="exhibit",
                thesis="Числовые факты показывают, где рыночный сигнал сильнее всего",
                narrative="Связанные числовые факты сгруппированы в сопоставимый рейтинг, а не оставлены сырой таблицей доказательств.",
                visual=PremiumPageVisual(
                    visual_type="ranking_bar",
                    title="Comparable numeric signal",
                    data={"points": series[:10]},
                    source_notes=_sources_from_facts(facts[:10]),
                ),
                implication="Самые крупные значения должны вести управленческое обсуждение; остальные уходят в приложение, если не меняют решение.",
                source_notes=_sources_from_facts(facts[:10]),
            )
        )
    if analysis is not None and analysis.conflicts:
        rows = [
            {
                "topic": conflict.topic,
                "importance": conflict.importance,
                "source_a": conflict.source_a,
                "source_b": conflict.source_b,
                "resolution": conflict.resolution_hint,
            }
            for conflict in analysis.conflicts[:6]
        ]
        pages.append(
            PremiumPage(
                page_type="exhibit",
                thesis="Решение зависит от нескольких нерешенных противоречий",
                narrative="Существенные расхождения вынесены в risk-style exhibit, чтобы они не потерялись в прозе.",
                visual=PremiumPageVisual(
                    visual_type="risk_heatmap",
                    title="Conflict and uncertainty heatmap",
                    data={"rows": rows},
                ),
                implication="Клиентская рекомендация должна прямо назвать, какие конфликты важны и какие данные изменят вывод.",
            )
        )
    if report.all_sources:
        pages.append(
            PremiumPage(
                page_type="exhibit",
                thesis="Качество источников определяет, насколько уверенно можно использовать вывод",
                narrative="Надежность источников отделена от содержательного вывода, чтобы не смешивать факт и интерпретацию.",
                visual=PremiumPageVisual(
                    visual_type="evidence_quality",
                    title="Source reliability mix",
                    data={
                        "points": [
                            {"label": key, "value": value}
                            for key, value in _source_reliability_counts(report).items()
                        ]
                    },
                    source_notes=[source.url or source.title for source in report.all_sources[:8]],
                ),
                implication="Если доминируют источники низкой надежности, отчет должен оставаться decision memo, а не финальным основанием для инвестиции.",
                source_notes=[source.url or source.title for source in report.all_sources[:8]],
            )
        )
    return pages


def _decision_pages(
    report: FinalReport,
    sections: list[PremiumPreparedSection],
) -> list[PremiumPage]:
    pages: list[PremiumPage] = []
    scenario = _scenario_table_from_report(report) or _find_first_block(sections, "scenario_matrix")
    if scenario is not None:
        pages.append(
            PremiumPage(
                page_type="exhibit",
                thesis="Сценарии 2026-2027: что должно измениться, чтобы вывод стал другим",
                narrative="Сценарная страница переводит прогноз из текста в набор условий, триггеров и последствий для решения.",
                visual=PremiumPageVisual(
                    visual_type="scenario_matrix",
                    title=scenario.title,
                    data={"columns": scenario.columns, "rows": scenario.rows},
                ),
                implication="Руководителю нужен не один прогноз, а условия перехода между базовым, позитивным и негативным сценариями.",
            )
        )
    decision = _find_first_block(sections, "decision_matrix")
    if decision is not None:
        pages.append(
            PremiumPage(
                page_type="exhibit",
                thesis="Решение: действовать, ждать или пересобрать позицию",
                narrative="Итоговая управленческая страница отделяет рекомендацию от доказательной базы и показывает, когда позицию надо менять.",
                visual=PremiumPageVisual(
                    visual_type="scenario_matrix",
                    title=decision.title,
                    data={"columns": decision.columns, "rows": decision.rows},
                ),
                implication=_compact_text(report.executive_summary.what_meta_adds, 320)
                or "Финальный отчет должен завершаться решением, а не реестром фактов.",
            )
        )
    return pages


def _scenario_table_from_report(report: FinalReport) -> PremiumPreparedBlock | None:
    for table in report.tables:
        title = table.title.lower()
        if "сценар" not in title:
            continue
        return PremiumPreparedBlock(
            kind="scenario_matrix",
            title=table.title,
            columns=table.columns,
            rows=table.rows,
            notes=[table.caption] if table.caption else [],
        )
    return None


def _find_first_block(
    sections: list[PremiumPreparedSection],
    kind: PremiumBlockKind,
) -> PremiumPreparedBlock | None:
    for section in sections:
        for block in section.blocks:
            if block.kind == kind:
                return block
    return None


def _appendix_pages(appendices: list[PremiumPreparedSection]) -> list[PremiumPage]:
    pages: list[PremiumPage] = []
    for appendix in appendices:
        block = appendix.blocks[0] if appendix.blocks else None
        pages.append(
            PremiumPage(
                page_type="appendix",
                thesis=appendix.title,
                narrative=appendix.purpose,
                visual=PremiumPageVisual(
                    visual_type="source_table",
                    title=block.title if block else appendix.title,
                    data={
                        "columns": block.columns if block else [],
                        "rows": block.rows[:30] if block else [],
                    },
                    source_notes=[],
                ),
                implication="Appendix material supports verification and should not replace the report storyline.",
            )
        )
    return pages


def _numeric_series_from_facts(facts: list[NumericFact]) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    seen: set[str] = set()
    for fact in facts:
        value = _number_from_text(fact.value)
        if value is None:
            continue
        label = _compact_text(f"{fact.metric}: {fact.subject}", 64)
        key = f"{label}:{value}"
        if key in seen:
            continue
        seen.add(key)
        points.append({"label": label, "value": value, "source": _first_fact_source(fact)})
    return points


def _sources_from_facts(facts: list[NumericFact]) -> list[str]:
    notes: list[str] = []
    for fact in facts:
        source = _first_fact_source(fact)
        if source and source not in notes:
            notes.append(source)
    return notes


def _source_reliability_counts(report: FinalReport) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for source in report.all_sources:
        counts[source.reliability] = counts.get(source.reliability, 0) + 1
    return counts


def _top_source_notes(report: FinalReport, analysis: AnalysisOutput | None) -> list[str]:
    notes = [number.source_ref for number in report.key_numbers_highlight[:4] if number.source_ref]
    if not notes and analysis is not None:
        notes = _sources_from_facts(_numeric_facts(analysis)[:4])
    if not notes:
        notes = [source.url or source.title for source in report.all_sources[:4]]
    return notes


def _fallback_body_for_section(section: PremiumPreparedSection, report: FinalReport) -> str:
    for block in section.blocks:
        if block.body:
            return block.body
    return report.main_synthesis


def _first_block_signal(section: PremiumPreparedSection) -> str:
    for block in section.blocks:
        if block.body:
            return _compact_text(block.body, 260)
        if block.rows:
            return f"{block.title}: {len(block.rows)} rows of supporting evidence."
    return "Use the following exhibits and appendix detail to validate this section."


def _dedupe_pages(pages: list[PremiumPage]) -> list[PremiumPage]:
    deduped: list[PremiumPage] = []
    seen: set[str] = set()
    for page in pages:
        key = f"{page.page_type}:{page.thesis}:{page.visual.visual_type if page.visual else 'none'}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(page)
    return deduped


def _section_from_spec(
    spec: PremiumSectionSpec,
    *,
    report: FinalReport,
    analysis: AnalysisOutput | None,
) -> PremiumPreparedSection:
    blocks: list[PremiumPreparedBlock] = []
    blocks.extend(_blocks_for_section(spec, report=report, analysis=analysis))
    if not blocks:
        blocks.append(
            PremiumPreparedBlock(
                kind="narrative",
                title=spec.title,
                body=_fallback_body_for(spec, report),
            )
        )
    return PremiumPreparedSection(
        id=spec.id,
        title=spec.title,
        purpose=spec.purpose,
        min_pages=spec.min_pages,
        blocks=blocks,
    )


def _blocks_for_section(
    spec: PremiumSectionSpec,
    *,
    report: FinalReport,
    analysis: AnalysisOutput | None,
) -> list[PremiumPreparedBlock]:
    if spec.id == "executive_summary":
        return [
            PremiumPreparedBlock(
                kind="narrative",
                title="Короткий ответ",
                body=report.executive_summary.main_answer,
            ),
            _kpi_grid(report, analysis),
            _decision_matrix(report),
        ]
    if spec.id == "question_framing":
        return [
            PremiumPreparedBlock(
                kind="methodology_box",
                title="Рамки и контекст решения",
                body=report.question,
                notes=[
                    "Премиальный документ должен разделять проверенные факты, интерпретацию и рекомендации.",
                    "Ограничения и недоступные данные должны быть видимыми частями материала.",
                ],
            )
        ]
    if spec.id == "evidence_base":
        return [_evidence_table(analysis), _source_quality_table(report)]
    if spec.id in {"market_baseline", "current_state", "context", "target_profile"}:
        return [
            PremiumPreparedBlock(
                kind="narrative",
                title="Базовый синтез",
                body=report.main_synthesis,
            ),
            _timeline_block(report),
        ]
    if spec.id in {"demand_supply", "analysis", "capability_benchmark"}:
        return [_consensus_table(analysis), _conflicts_table(analysis)]
    if spec.id in {"scenarios", "strategic_options", "valuation_and_exit"}:
        return [_scenario_matrix(report), _sensitivity_table(analysis)]
    if spec.id in {"findings", "diligence_findings", "risk_interpretation"}:
        return [_conflicts_table(analysis), _risk_register(report, analysis)]
    if spec.id in {"recommendations", "risk_adjusted_decision", "go_no_go"}:
        return [_decision_matrix(report), _risk_register(report, analysis)]
    if spec.id in {"risks_and_monitoring", "roadmap", "remediation", "compliance_actions"}:
        return [_risk_register(report, analysis), _timeline_block(report)]
    if spec.id in {"competitive_landscape", "strategic_moves"}:
        return [_generic_matrix("Competitive / option matrix", "competitive_matrix", analysis)]
    if spec.id in {"investment_thesis", "asset_or_target_profile", "system_map", "regulatory_baseline"}:
        return [_kpi_grid(report, analysis), _evidence_table(analysis)]
    return []


def _kpi_grid(report: FinalReport, analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows: list[list[str]] = []
    for number in report.executive_summary.key_numbers:
        rows.append([number.metric, number.value, number.subject, number.source_url])
    for fact in _numeric_facts(analysis)[:8]:
        rows.append([fact.metric, fact.value, fact.subject, _first_fact_source(fact)])
    return PremiumPreparedBlock(
        kind="kpi_grid",
        title="Ключевые метрики",
        columns=["Метрика", "Значение", "Объект", "Источник"],
        rows=rows,
        notes=["Пустые строки означают, что аналитический слой не передал достаточно числовых фактов."],
    )


def _evidence_table(analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows = [
        [
            fact.fact_id,
            fact.value,
            fact.metric,
            fact.subject,
            fact.timeframe or "",
            fact.relevance_to_question,
            _first_fact_source(fact),
        ]
        for fact in _numeric_facts(analysis)[:30]
    ]
    return PremiumPreparedBlock(
        kind="evidence_table",
        title="Реестр числовых доказательств",
        columns=["ID", "Значение", "Метрика", "Объект", "Период", "Релевантность", "Источник"],
        rows=rows,
    )


def _source_quality_table(report: FinalReport) -> PremiumPreparedBlock:
    rows = [
        [source.title, source.url, source.tool, source.reliability]
        for source in (report.all_sources or [])
    ]
    return PremiumPreparedBlock(
        kind="source_quality_table",
        title="Реестр качества источников",
        columns=["Источник", "URL", "Инструмент", "Надёжность"],
        rows=rows,
    )


def _consensus_table(analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows = []
    if analysis is not None:
        rows = [
            [claim.claim, claim.confidence, ", ".join(claim.supporting_sources)]
            for claim in analysis.consensus
        ]
    return PremiumPreparedBlock(
        kind="evidence_table",
        title="Согласованные утверждения",
        columns=["Утверждение", "Уверенность", "Поддерживающие источники"],
        rows=rows,
    )


def _conflicts_table(analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows = []
    if analysis is not None:
        rows = [
            [
                conflict.topic,
                conflict.source_a,
                conflict.claim_a,
                conflict.source_b,
                conflict.claim_b,
                conflict.importance,
                conflict.resolution_hint,
            ]
            for conflict in analysis.conflicts
        ]
    return PremiumPreparedBlock(
        kind="evidence_table",
        title="Противоречия и расхождения",
        columns=["Тема", "Источник A", "Утверждение A", "Источник B", "Утверждение B", "Важность", "Разрешение"],
        rows=rows,
    )


def _scenario_matrix(report: FinalReport) -> PremiumPreparedBlock:
    rows = [
        ["Базовый", "Наиболее вероятная интерпретация доказательств", report.executive_summary.main_answer],
        ["Оптимистичный", "Условия, при которых вывод улучшается", "См. рекомендации и триггеры мониторинга."],
        ["Пессимистичный", "Условия, при которых вывод теряет силу", "См. реестр рисков и открытые ограничения."],
    ]
    return PremiumPreparedBlock(
        kind="scenario_matrix",
        title="Матрица сценариев",
        columns=["Сценарий", "Определение", "Следствие"],
        rows=rows,
    )


def _sensitivity_table(analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows: list[list[str]] = []
    if analysis is not None:
        for fact in analysis.high_relevance_facts[:8]:
            source = _first_fact_source(fact)
            rows.append(
                [
                    fact.metric,
                    fact.value,
                    fact.subject,
                    source or "Источник не указан",
                ]
            )
    return PremiumPreparedBlock(
        kind="sensitivity_table",
        title="Рамка чувствительности",
        columns=["Драйвер", "Базовое значение", "К чему относится", "Источник / проверка"],
        rows=rows,
        notes=[
            "Это не имитация точной модели чувствительности: показаны факторы, по которым есть числовая база. "
            "Пороговые сценарные дельты должны добавляться только при наличии источников или явной модели."
        ],
    )


def _decision_matrix(report: FinalReport) -> PremiumPreparedBlock:
    findings = report.executive_summary.top_findings or []
    rows = [
        [
            "Действовать",
            "Доказательства поддерживают действие",
            _compact_text(findings[0] if findings else report.executive_summary.main_answer, 280),
        ],
        [
            "Ждать",
            "Ключевой триггер не выполнен",
            _compact_text(report.gaps_filled_section or "Остаются открытые вопросы.", 280),
        ],
        [
            "Отказаться / пересобрать",
            "Критический риск становится главным",
            _compact_text(report.conflicts_section or "Критическое противоречие не указано.", 280),
        ],
    ]
    return PremiumPreparedBlock(
        kind="decision_matrix",
        title="Матрица решений",
        columns=["Действие", "Условие", "Обоснование"],
        rows=rows,
    )


def _compact_text(value: str, limit: int = 320) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip(" ,.;:") + "…"


def _risk_register(report: FinalReport, analysis: AnalysisOutput | None) -> PremiumPreparedBlock:
    rows: list[list[str]] = []
    if analysis is not None:
        rows.extend(
            [gap.topic, "Пробел в доказательствах", gap.why_critical, gap.what_to_find]
            for gap in analysis.gaps
        )
        rows.extend(
            [
                conflict.topic,
                f"Противоречие: {conflict.importance}",
                conflict.claim_a,
                conflict.resolution_hint,
            ]
            for conflict in analysis.conflicts
        )
    if report.gaps_filled_section and not rows:
        rows.append(["Открытое ограничение", "Пробел", report.gaps_filled_section, "Отслеживать до решения."])
    return PremiumPreparedBlock(
        kind="risk_register",
        title="Реестр рисков",
        columns=["Риск / тема", "Тип", "Почему важно", "Снижение риска / мониторинг"],
        rows=rows,
    )


def _timeline_block(report: FinalReport) -> PremiumPreparedBlock:
    return PremiumPreparedBlock(
        kind="timeline",
        title="Лента мониторинга",
        columns=["Этап", "Что проверить", "Зачем"],
        rows=[
            ["Сейчас", "Проверить покрытие источниками и нерешённые пробелы", "Избежать ложной точности."],
            ["Следующее обновление", "Обновить ключевые факты и триггеры", "Увидеть смену сценария."],
            ["Точка решения", "Применить матрицу решений", "Перевести анализ в действие."],
        ],
        notes=[report.executive_summary.confidence_note] if report.executive_summary.confidence_note else [],
    )


def _generic_matrix(
    title: str,
    kind: PremiumBlockKind,
    analysis: AnalysisOutput | None,
) -> PremiumPreparedBlock:
    rows = []
    if analysis is not None:
        rows = [[claim.claim, claim.confidence, ", ".join(claim.supporting_sources)] for claim in analysis.consensus]
    return PremiumPreparedBlock(
        kind=kind,
        title=title,
        columns=["Параметр", "Оценка", "Доказательство"],
        rows=rows,
    )


def _appendix_sections(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None,
) -> list[PremiumPreparedSection]:
    return [
        PremiumPreparedSection(
            id="appendix_sources",
            title="Приложение A: источники",
            purpose="Полный реестр источников для проверки.",
            min_pages=1,
            blocks=[_source_quality_table(report)],
        ),
        PremiumPreparedSection(
            id="appendix_facts",
            title="Приложение B: фактологическая база",
            purpose="Извлечённые числовые факты и ссылки на источники.",
            min_pages=1,
            blocks=[_evidence_table(analysis)],
        ),
        PremiumPreparedSection(
            id="appendix_limits",
            title="Приложение C: ограничения",
            purpose="Известные пробелы, ограничения и нерешённые расхождения.",
            min_pages=1,
            blocks=[_risk_register(report, analysis)],
        ),
    ]


def _deck_slides(plan: PremiumReportPlan) -> list[PremiumDeckSlideSpec]:
    slides: list[PremiumDeckSlideSpec] = []
    section_ids = [section.id for section in plan.sections]
    for index, title in enumerate(plan.deck_outline):
        source_section_id = section_ids[min(index, len(section_ids) - 1)] if section_ids else None
        slides.append(
            PremiumDeckSlideSpec(
                title=title,
                objective="Слайд для руководителя, производный от полного отчёта.",
                source_section_id=source_section_id,
                suggested_blocks=_suggested_blocks_for_slide(title),
            )
        )
    return slides


def _suggested_blocks_for_slide(title: str) -> list[PremiumBlockKind]:
    lower = title.lower()
    if "evidence" in lower or "confidence" in lower or "доказ" in lower or "увер" in lower:
        return ["source_quality_table"]
    if "risk" in lower or "риск" in lower:
        return ["risk_register"]
    if "decision" in lower or "решен" in lower or "решени" in lower:
        return ["decision_matrix"]
    if "scenario" in lower or "option" in lower or "сценар" in lower or "вариант" in lower:
        return ["scenario_matrix"]
    if "visual" in lower or "key" in lower or "визуал" in lower or "ключ" in lower:
        return ["kpi_grid"]
    return ["narrative"]


def _title_for(report: FinalReport) -> str:
    question = " ".join((report.question or "").split())
    return question[:120] if question else "Премиальный аналитический отчёт"


def _subtitle_for(plan: PremiumReportPlan) -> str:
    return (
        f"{_report_type_label(plan.report_type)} для аудитории: {_audience_label(plan.audience)}"
    )


def _fallback_body_for(spec: PremiumSectionSpec, report: FinalReport) -> str:
    if report.main_synthesis:
        return report.main_synthesis
    return f"{spec.purpose} Этот раздел требует дополнительного собранного материала."


def _audience_label(audience: str) -> str:
    return {
        "buyer": "покупатель",
        "investor": "инвестор",
        "executive": "руководитель",
        "operator": "оператор",
        "developer": "девелопер",
        "analyst": "аналитик",
        "technical_lead": "технический руководитель",
        "general_client": "клиент",
    }.get(audience, audience.replace("_", " "))


def _report_type_label(report_type: str) -> str:
    return {
        "market": "Рыночный анализ",
        "investment": "Инвестиционный анализ",
        "competitive": "Конкурентный анализ",
        "strategy": "Стратегический отчёт",
        "technical_audit": "Технический аудит",
        "legal_regulatory": "Правовой и регуляторный анализ",
        "due_diligence": "Due diligence",
        "general_research": "Исследование",
    }.get(report_type, report_type.replace("_", " ").title())


def _numeric_facts(analysis: AnalysisOutput | None) -> list[NumericFact]:
    if analysis is None:
        return []
    return list(analysis.high_relevance_facts or analysis.all_numeric_facts)


def _first_fact_source(fact: NumericFact) -> str:
    if not fact.sources:
        return ""
    ref = fact.sources[0]
    return ref.url or ref.title or ""


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
