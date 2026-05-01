"""Universal planner for premium client deliverables.

The planner is deliberately heuristic and side-effect free. It creates a
domain-neutral premium report/deck plan from a final report question and, when
available, evidence metadata. Renderers can use the plan later, but this module
does not modify existing export behavior.
"""

from __future__ import annotations

import re

from ...models import AnalysisOutput, FinalReport
from .models import (
    PremiumAppendixSpec,
    PremiumAudience,
    PremiumDeliverableSpec,
    PremiumEvidenceRequirement,
    PremiumReportPlan,
    PremiumReportType,
    PremiumSectionSpec,
    PremiumVisualSpec,
)


def build_premium_report_plan(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
    min_report_pages: int = 20,
    min_deck_slides: int = 10,
) -> PremiumReportPlan:
    """Build an opt-in premium report plan without touching legacy exporters."""

    question = report.question or ""
    report_type = infer_report_type(question, report)
    audience = infer_audience(question)
    decision_context = _decision_context(question, report_type, audience)

    sections = _base_sections(report_type)
    required_visuals = _visuals_for(report_type)
    appendices = _appendices_for(report_type)
    deck_outline = _deck_outline_for(report_type)

    source_count = len(report.all_sources or [])
    fact_count = _fact_count(analysis)
    evidence = PremiumEvidenceRequirement(
        min_sources=max(8, min(source_count + 3, 15)),
        min_authoritative_sources=3,
        min_numeric_facts=max(20, min(fact_count + 10, 60)),
    )

    return PremiumReportPlan(
        report_type=report_type,
        audience=audience,
        decision_context=decision_context,
        deliverables=PremiumDeliverableSpec(
            report_min_pages=max(20, min_report_pages),
            deck_min_slides=max(10, min_deck_slides),
        ),
        evidence=evidence,
        sections=sections,
        required_visuals=required_visuals,
        appendices=appendices,
        deck_outline=deck_outline,
        non_breaking_notes=[
            "Report and deck are separate client deliverables.",
            "Publication-grade PDF quality is required in addition to editable DOCX.",
            "Премиальный слой включается отдельно и не меняет поведение старых экспортов.",
            "Отчёт и презентация являются разными материалами, а не заменяют друг друга.",
            "Факты по теме должны жить в таблицах доказательств, а не в коде рендерера.",
        ],
    )


def infer_report_type(question: str, report: FinalReport | None = None) -> PremiumReportType:
    text = _combined_text(question, report)
    if _has(text, "рынок", "market", "цены", "price", "demand", "supply", "forecast"):
        return "market"
    if _has(text, "инвест", "investment", "irr", "доход", "valuation", "окуп"):
        return "investment"
    if _has(text, "конкур", "competitor", "competitive", "benchmark", "позициони"):
        return "competitive"
    if _has(text, "стратег", "strategy", "go-to-market", "roadmap", "рост"):
        return "strategy"
    if _has(text, "код", "архитект", "security", "аудит", "bug", "technical", "repo"):
        return "technical_audit"
    if _has(text, "закон", "регуля", "legal", "compliance", "налог", "санкц"):
        return "legal_regulatory"
    if _has(text, "due diligence", "провер", "risk", "риски", "сделк"):
        return "due_diligence"
    return "general_research"


def infer_audience(question: str) -> PremiumAudience:
    text = question.lower()
    if _has(text, "покуп", "buyer", "купить"):
        return "buyer"
    if _has(text, "инвест", "investor", "irr", "доход"):
        return "investor"
    if _has(text, "ceo", "директор", "executive", "совет"):
        return "executive"
    if _has(text, "developer", "девелоп", "застрой"):
        return "developer"
    if _has(text, "cto", "tech lead", "инженер", "архитектор", "repo", "security", "bug"):
        return "technical_lead"
    if _has(text, "операц", "operator", "ops"):
        return "operator"
    if _has(text, "аналит", "analyst"):
        return "analyst"
    return "general_client"


def _base_sections(report_type: PremiumReportType) -> list[PremiumSectionSpec]:
    common = [
        PremiumSectionSpec(
            id="executive_summary",
            title="Резюме для решения",
            purpose="Коротко зафиксировать ответ, последствия для решения и уровень уверенности.",
            min_pages=1,
            required_blocks=["kpi_grid", "decision_matrix"],
        ),
        PremiumSectionSpec(
            id="question_framing",
            title="Вопрос, рамки и методология",
            purpose="Уточнить, на какой вопрос отвечает отчёт, для кого он подготовлен и что осталось вне рамок.",
            min_pages=1,
            required_blocks=["methodology_box"],
        ),
        PremiumSectionSpec(
            id="evidence_base",
            title="Доказательная база",
            purpose="Показать факты, уровни надёжности источников и ограничения данных.",
            min_pages=2,
            required_blocks=["evidence_table", "source_quality_table"],
        ),
    ]

    type_specific: dict[PremiumReportType, list[PremiumSectionSpec]] = {
        "market": [
            PremiumSectionSpec(
                id="market_baseline",
                title="Базовая картина рынка",
                purpose="Определить рынок, сегменты, историческую динамику и текущее состояние.",
                min_pages=3,
                required_blocks=["timeline", "chart"],
            ),
            PremiumSectionSpec(
                id="demand_supply",
                title="Драйверы спроса и предложения",
                purpose="Объяснить, какие силы двигают рынок и какие из них доминируют.",
                min_pages=3,
                required_blocks=["market_map", "chart"],
            ),
            PremiumSectionSpec(
                id="scenarios",
                title="Сценарный прогноз",
                purpose="Смоделировать базовый, оптимистичный и пессимистичный исходы с триггерами.",
                min_pages=3,
                required_blocks=["scenario_matrix", "sensitivity_table"],
            ),
        ],
        "investment": [
            PremiumSectionSpec(
                id="investment_thesis",
                title="Инвестиционный тезис",
                purpose="Определить потенциал роста, негативный сценарий, условия входа и логику доходности.",
                min_pages=3,
                required_blocks=["kpi_grid", "sensitivity_table"],
            ),
            PremiumSectionSpec(
                id="valuation_and_exit",
                title="Оценка стоимости и выход",
                purpose="Объяснить цену, доходность, ликвидность и предпосылки выхода.",
                min_pages=3,
                required_blocks=["scenario_matrix", "chart"],
            ),
            PremiumSectionSpec(
                id="risk_adjusted_decision",
                title="Решение с учётом риска",
                purpose="Перевести анализ в пороги: инвестировать, ждать или отказаться.",
                min_pages=2,
                required_blocks=["risk_register", "decision_matrix"],
            ),
        ],
        "competitive": [
            PremiumSectionSpec(
                id="competitive_landscape",
                title="Конкурентная карта",
                purpose="Сопоставить конкурентов, сегменты, позиционирование и стратегическое давление.",
                min_pages=3,
                required_blocks=["competitive_matrix", "market_map"],
            ),
            PremiumSectionSpec(
                id="capability_benchmark",
                title="Бенчмарк возможностей",
                purpose="Сравнить сильные стороны, пробелы, цены, дистрибуцию и глубину продукта.",
                min_pages=3,
                required_blocks=["competitive_matrix", "chart"],
            ),
            PremiumSectionSpec(
                id="strategic_moves",
                title="Стратегические ходы",
                purpose="Рекомендовать действия, компромиссы и последовательность шагов.",
                min_pages=2,
                required_blocks=["decision_matrix", "risk_register"],
            ),
        ],
        "strategy": [
            PremiumSectionSpec(
                id="current_state",
                title="Текущее состояние",
                purpose="Определить операционный контекст и ограничения.",
                min_pages=2,
                required_blocks=["kpi_grid", "market_map"],
            ),
            PremiumSectionSpec(
                id="strategic_options",
                title="Стратегические варианты",
                purpose="Сравнить реалистичные стратегические пути и компромиссы.",
                min_pages=3,
                required_blocks=["decision_matrix", "scenario_matrix"],
            ),
            PremiumSectionSpec(
                id="roadmap",
                title="Дорожная карта и операционные метрики",
                purpose="Перевести стратегию в этапы и измеримые показатели.",
                min_pages=2,
                required_blocks=["timeline", "risk_register"],
            ),
        ],
        "technical_audit": [
            PremiumSectionSpec(
                id="system_map",
                title="Карта системы",
                purpose="Объяснить архитектуру, границы доверия и операционный поток.",
                min_pages=3,
                required_blocks=["market_map", "evidence_table"],
            ),
            PremiumSectionSpec(
                id="findings",
                title="Находки и критичность",
                purpose="Приоритизировать ошибки, риски, регрессии и недостающую проверку.",
                min_pages=4,
                required_blocks=["risk_register", "evidence_table"],
            ),
            PremiumSectionSpec(
                id="remediation",
                title="План исправлений и проверки",
                purpose="Определить исправления, владельцев, тесты и релизные гейты.",
                min_pages=2,
                required_blocks=["timeline", "decision_matrix"],
            ),
        ],
        "legal_regulatory": [
            PremiumSectionSpec(
                id="regulatory_baseline",
                title="Регуляторная база",
                purpose="Суммировать действующие правила и авторитетные источники.",
                min_pages=3,
                required_blocks=["evidence_table", "source_quality_table"],
            ),
            PremiumSectionSpec(
                id="risk_interpretation",
                title="Интерпретация рисков",
                purpose="Перевести правила в операционные и финансовые риски.",
                min_pages=3,
                required_blocks=["risk_register", "scenario_matrix"],
            ),
            PremiumSectionSpec(
                id="compliance_actions",
                title="Действия по соответствию",
                purpose="Определить пороги действий, мониторинг и эскалацию.",
                min_pages=2,
                required_blocks=["decision_matrix", "timeline"],
            ),
        ],
        "due_diligence": [
            PremiumSectionSpec(
                id="asset_or_target_profile",
                title="Профиль объекта проверки",
                purpose="Определить объект проверки и его доказательный след.",
                min_pages=2,
                required_blocks=["kpi_grid", "evidence_table"],
            ),
            PremiumSectionSpec(
                id="diligence_findings",
                title="Выводы проверки",
                purpose="Оценить сильные стороны, слабости, неизвестные зоны и красные флаги.",
                min_pages=4,
                required_blocks=["risk_register", "source_quality_table"],
            ),
            PremiumSectionSpec(
                id="go_no_go",
                title="Решение go / no-go",
                purpose="Определить условия продолжения, пересмотра сделки или отказа.",
                min_pages=2,
                required_blocks=["decision_matrix", "sensitivity_table"],
            ),
        ],
        "general_research": [
            PremiumSectionSpec(
                id="context",
                title="Контекст и базовая линия",
                purpose="Зафиксировать известные факты и контекст решения.",
                min_pages=3,
                required_blocks=["timeline", "evidence_table"],
            ),
            PremiumSectionSpec(
                id="analysis",
                title="Анализ",
                purpose="Развить основную аргументацию и сравнить интерпретации.",
                min_pages=4,
                required_blocks=["chart", "decision_matrix"],
            ),
            PremiumSectionSpec(
                id="implications",
                title="Последствия для решения",
                purpose="Перевести выводы в действия и мониторинг.",
                min_pages=2,
                required_blocks=["risk_register", "timeline"],
            ),
        ],
    }

    closing = [
        PremiumSectionSpec(
            id="recommendations",
            title="Рекомендации и пороги решения",
            purpose="Дать конкретные правила действия, а не общие советы.",
            min_pages=2,
            required_blocks=["decision_matrix"],
        ),
        PremiumSectionSpec(
            id="risks_and_monitoring",
            title="Риски и мониторинг",
            purpose="Показать, что может изменить выводы и как это отслеживать.",
            min_pages=2,
            required_blocks=["risk_register", "timeline"],
        ),
        PremiumSectionSpec(
            id="appendix",
            title="Приложения",
            purpose="Дать источники, факты и расчётную базу для проверки.",
            min_pages=3,
            required_blocks=["appendix_table"],
        ),
    ]

    return common + type_specific[report_type] + closing


def _visuals_for(report_type: PremiumReportType) -> list[PremiumVisualSpec]:
    visuals = [
        PremiumVisualSpec(
            kind="kpi_grid",
            title="Ключевые метрики",
            purpose="Сделать выводы быстрыми для чтения и численно обоснованными.",
        ),
        PremiumVisualSpec(
            kind="evidence_table",
            title="Таблица доказательств",
            purpose="Связать ключевые утверждения с источниками и уровнями надёжности.",
        ),
        PremiumVisualSpec(
            kind="decision_matrix",
            title="Матрица решений",
            purpose="Перевести анализ в действия клиента.",
        ),
        PremiumVisualSpec(
            kind="risk_register",
            title="Реестр рисков",
            purpose="Показать негативные сценарии, важность, меры снижения и мониторинг.",
        ),
    ]
    if report_type in {"market", "investment", "strategy", "due_diligence"}:
        visuals.append(
            PremiumVisualSpec(
                kind="scenario_matrix",
                title="Матрица сценариев",
                purpose="Разделить базовый, позитивный и негативный исходы.",
            )
        )
        visuals.append(
            PremiumVisualSpec(
                kind="sensitivity_table",
                title="Таблица чувствительности",
                purpose="Показать, как выводы меняются при сдвиге ключевых предпосылок.",
            )
        )
    if report_type == "competitive":
        visuals.append(
            PremiumVisualSpec(
                kind="competitive_matrix",
                title="Конкурентная матрица",
                purpose="Сравнить игроков по действительно важным параметрам.",
            )
        )
    if report_type == "technical_audit":
        visuals.append(
            PremiumVisualSpec(
                kind="timeline",
                title="Дорожная карта исправлений",
                purpose="Показать последовательность исправлений и контрольные точки проверки.",
            )
        )
    return visuals


def _appendices_for(report_type: PremiumReportType) -> list[PremiumAppendixSpec]:
    appendices = [
        PremiumAppendixSpec(
            title="Фактологическая база",
            purpose="Полный список извлечённых утверждений, чисел и ссылок на источники.",
        ),
        PremiumAppendixSpec(
            title="Реестр качества источников",
            purpose="Уровень надёжности, релевантность и ограничения каждого источника.",
        ),
        PremiumAppendixSpec(
            title="Открытые вопросы и недоступные данные",
            purpose="Убрать ложную точность и показать, что ещё не верифицировано.",
        ),
    ]
    if report_type in {"market", "investment", "strategy"}:
        appendices.append(
            PremiumAppendixSpec(
                title="Приложение по предпосылкам и чувствительности",
                purpose="Зафиксировать входные предпосылки сценариев и сдвиги выводов.",
            )
        )
    if report_type in {"technical_audit", "legal_regulatory", "due_diligence"}:
        appendices.append(
            PremiumAppendixSpec(
                title="Реестр проблем",
                purpose="Подробный список находок с критичностью и статусом исправления.",
            )
        )
    return appendices


def _deck_outline_for(report_type: PremiumReportType) -> list[str]:
    base = [
        "Титул и вопрос решения",
        "Короткий ответ",
        "Что изменилось или что важнее всего",
        "Доказательная база и уверенность",
        "Ключевой визуал 1",
        "Ключевой визуал 2",
        "Сценарии или варианты",
        "Матрица решений",
        "Риски и контрольные индикаторы",
        "Рекомендуемые следующие шаги",
    ]
    if report_type == "technical_audit":
        base[4] = "Архитектура / карта системы"
        base[5] = "Находки по критичности (severity)"
        base[6] = "Дорожная карта исправлений"
    elif report_type == "competitive":
        base[4] = "Карта рынка"
        base[5] = "Бенчмарк конкурентов"
        base[6] = "Стратегические варианты"
    return base


def _combined_text(question: str, report: FinalReport | None) -> str:
    chunks = [question]
    if report is not None:
        chunks.extend(
            [
                report.executive_summary.main_answer,
                report.main_synthesis,
                report.consensus_section,
                report.conflicts_section,
            ]
        )
    return " ".join(chunks).lower()


def _has(text: str, *needles: str) -> bool:
    return any(needle.lower() in text for needle in needles)


def _decision_context(
    question: str,
    report_type: PremiumReportType,
    audience: PremiumAudience,
) -> str:
    clean = re.sub(r"\s+", " ", question).strip()
    if clean:
        return f"Помочь аудитории «{_audience_label(audience)}» ответить на вопрос: {clean}"
    return f"Помочь аудитории «{_audience_label(audience)}» принять решение по типу отчёта «{_report_type_label(report_type)}»."


def _audience_label(audience: PremiumAudience) -> str:
    return {
        "buyer": "покупатель",
        "investor": "инвестор",
        "executive": "руководитель",
        "operator": "оператор",
        "developer": "девелопер",
        "analyst": "аналитик",
        "technical_lead": "технический руководитель",
        "general_client": "клиент",
    }.get(audience, str(audience).replace("_", " "))


def _report_type_label(report_type: PremiumReportType) -> str:
    return {
        "market": "рыночный анализ",
        "investment": "инвестиционный анализ",
        "competitive": "конкурентный анализ",
        "strategy": "стратегия",
        "technical_audit": "технический аудит",
        "legal_regulatory": "правовой и регуляторный анализ",
        "due_diligence": "due diligence",
        "general_research": "исследование",
    }.get(report_type, str(report_type).replace("_", " "))


def _fact_count(analysis: AnalysisOutput | None) -> int:
    if analysis is None:
        return 0
    high = getattr(analysis, "high_relevance_facts", None) or []
    all_facts = getattr(analysis, "all_numeric_facts", None) or []
    return len(high or all_facts)
