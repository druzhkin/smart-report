"""Assemble a renderer-neutral premium report document.

The document assembler reuses the existing v4 analytical layer instead of
replacing it: executive answer, consensus, conflicts, gaps, numeric facts,
sources, bibliography, tables, charts, and metadata all flow into a richer
section/block structure. Renderers can target DOCX/PDF/PPTX later without
needing topic-specific logic.
"""

from __future__ import annotations

from ...models import AnalysisOutput, FinalReport, NumericFact
from .models import (
    PremiumBlockKind,
    PremiumDeckSlideSpec,
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

    return PremiumReportDocument(
        title=_title_for(report),
        subtitle=_subtitle_for(plan),
        plan=plan,
        sections=sections,
        appendices=appendices,
        deck_slides=deck_slides,
        source_count=len(report.all_sources or []),
        numeric_fact_count=len(numeric_facts),
        premium_readiness=premium_readiness,
    )


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
