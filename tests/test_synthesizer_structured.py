"""Unit tests for Synthesizer structured output (Track A).

Tests that Synthesizer correctly parses and coerces new structured fields:
qa_section, ranking, tables, charts, callouts, key_numbers_highlight.

DoD thresholds per spec §4.A.4:
- qa_section: >= 4 items
- tables: >= 3 tables
- charts: >= 3 ChartSpec
- callouts: >= 3 insights
- key_numbers_highlight: 5-7 items
- ranking: structured with weights
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from smart_report import synthesizer as synth_module
from smart_report.llm import LLMResult
from smart_report.models import (
    AnalysisOutput,
    CalloutBlock,
    ChartSpec,
    ConsensusClaim,
    FinalReport,
    KeyNumberHighlight,
    QAItem,
    RankingItem,
    ResearchPrompt,
    Table,
    UploadedMarkdown,
    V4Session,
)
from smart_report.synthesizer import (
    _coerce_callouts,
    _coerce_charts,
    _coerce_key_numbers_highlight,
    _coerce_qa_section,
    _coerce_ranking,
    _coerce_tables,
    synthesize_final_report,
)


# ---------------------------------------------------------------------------
# The user's real question with 5 explicit sub-questions (spec §3)
# ---------------------------------------------------------------------------
AMENITIES_QUESTION = (
    "мне нужен полный глубокий обзор по бизнес и премиум новостройкам москвы и анализ "
    "мировых практик – нужно понять, что реально пользуется спросом у покупателей а что "
    "нет, какие параметры комплекса: архитектура, фасады, мопы, финтес, бассейны, "
    "сигарные, и прочее. Какие именно параметры проекта, инфраструктуры и аменитис "
    "реально нужны и сколько покупатели готовы за это платить через рост цены. Есть ли "
    "оптимальный баланс в ассртименте аменитис, есть ли потимальный экономический баланс "
    "для застройщика по аменитис (потеря площадей, влияние на цену, окупаемоть аменитис)."
)

# ---------------------------------------------------------------------------
# Full mock FinalReport JSON matching the new schema
# ---------------------------------------------------------------------------
_MOCK_STRUCTURED_JSON = {
    "session_id": "will-be-overridden",
    "question": AMENITIES_QUESTION,
    "research_prompt_used": "Analyse Moscow amenities market 2024.",
    "executive_summary": {
        "main_answer": (
            "В московских бизнес/премиум-новостройках 2024 года доказанный спрос "
            "формируют три категории: закрытая территория (+7–12% к цене), качественные "
            "МОПы (+8–15%), и фитнес-центр (+3–5%). Бассейны и сигарные — имиджевые "
            "позиции с отрицательным ROI для большинства проектов бизнес-класса. "
            "Оптимальный CAPEX на amenities — 3–5% от себестоимости строительства."
        ),
        "ranking": None,
        "top_findings": [
            "Закрытая охраняемая территория даёт +7–12% к цене квартир [консенсус 3 источников]",
            "МОПы отель-класса: ценовая премия +8–15% при CAPEX 2–3% от сметы [OpenAI DR]",
            "Фитнес-центр: +3–5% к цене, OPEX умеренный [Perplexity]",
            "Бассейн: CAPEX в 4× выше фитнеса, ценовая премия всего +2–4% [Claude]",
            "Оптимальный набор amenities для бизнес-класса: 5–7 позиций [аналитика]",
        ],
        "key_numbers": [
            {
                "value": "+12%",
                "metric": "ценовая премия",
                "subject": "закрытая территория бизнес-класс",
                "source_url": "",
            },
            {
                "value": "3–5%",
                "metric": "оптимальный CAPEX на amenities",
                "subject": "застройщик бизнес-класс",
                "source_url": "",
            },
        ],
        "confidence_note": "Средний уровень доверия: цифры из vendor-отчётов брокеров.",
        "what_meta_adds": (
            "Reconciled три оценки ценовой премии фитнеса (3%, 5%, 8%) — "
            "принято 3–5% как наиболее подтверждённый диапазон."
        ),
    },
    "main_synthesis": (
        "## Тезис\n\nАmenities в бизнес-классе — не опция, а ценообразующий фактор.\n\n"
        "## Иерархия спроса\n\nЗакрытая территория лидирует по соотношению CAPEX/премия...\n\n"
        "## Экономика застройщика\n\nОптимальный бюджет 3–5% от себестоимости...\n\n"
        "## Ценовые премии\n\nОт +2% (сигарная) до +15% (МОПы отель-класса)...\n\n"
        "## Оптимальный баланс\n\n5–7 amenities — точка убывающей отдачи...\n\n"
        "## Implications\n\nЗастройщику рекомендуется инвестировать в топ-3 категории..."
    ),
    "consensus_section": "Все три источника согласны: закрытая территория и фитнес — must-have.",
    "conflicts_section": "Конфликт по ценовой премии от бассейна: 2% (Perplexity) vs 6% (OpenAI DR). Принято 2–4%.",
    "gaps_filled_section": "Добор не проводился. Оставшиеся gaps: данные по окупаемости сигарных комнат.",
    "all_sources": [
        {
            "title": "Анализ московского рынка amenities 2024",
            "url": "https://example.com/amenities",
            "tool": "perplexity",
            "reliability": "medium",
        },
        {
            "title": "Premium Moscow newbuilds DR",
            "url": "https://example.com/premium",
            "tool": "openai_dr",
            "reliability": "medium",
        },
    ],
    "metadata": {"source_reports_count": 4},
    # NEW structured fields
    "qa_section": [
        {
            "question": "Что реально пользуется спросом у покупателей, а что нет?",
            "answer": (
                "Доказанный спрос: закрытая территория, качественные МОПы, фитнес. "
                "Нишевый/имиджевый: бассейн, сигарная, wine room. "
                "Практически нет спроса: butler service в масс-маркете бизнес-класса."
            ),
            "details_ref": "Раздел «Иерархия спроса» в main_synthesis",
        },
        {
            "question": "Какие именно параметры нужны — архитектура, фасады, МОПы, фитнес, бассейны, сигарные?",
            "answer": (
                "Приоритет 1 (must-have): архитектура/фасады, закрытая территория, МОПы. "
                "Приоритет 2 (strong ROI): фитнес, консьерж, детская. "
                "Приоритет 3 (image/nice-to-have): бассейн, сигарная, коворкинг."
            ),
            "details_ref": "Таблица «Amenities по приоритету и ROI»",
        },
        {
            "question": "Сколько покупатели готовы платить — ценовая премия?",
            "answer": (
                "За полный набор amenities топ-уровня покупатель платит +8–18% к «голому» ЖК. "
                "Максимум в ультра-премиум — 25–30% с full-service. "
                "Минимум за отдельную amenity: +1–2% (сигарная комната)."
            ),
            "details_ref": "Раздел «Ценовые премии» в main_synthesis",
        },
        {
            "question": "Есть ли оптимальный баланс в ассортименте amenities?",
            "answer": (
                "Оптимум для бизнес-класса: 5–7 amenities из топ-категорий. "
                "После 8-й закон убывающей отдачи: <1% к цене, +3–5% OPEX в год. "
                "Ключевой принцип: качество каждой amenity важнее их количества."
            ),
            "details_ref": "Раздел «Оптимальный баланс» в main_synthesis",
        },
        {
            "question": "Есть ли оптимальный экономический баланс для застройщика по amenities?",
            "answer": (
                "Оптимальный CAPEX: 3–5% от общей себестоимости строительства. "
                "Этот бюджет даёт ценовую премию 8–15%, окупаемость 1.5–2×. "
                "Бассейн и сигарные — outlier: CAPEX высокий, ROI ниже порога для бизнес-класса."
            ),
            "details_ref": "Раздел «Экономика застройщика» в main_synthesis",
        },
    ],
    "ranking": [
        {
            "label": "Закрытая охраняемая территория",
            "weight": 25,
            "rationale": "Наибольшая ценовая премия (+7–12%), наименьший OPEX, консенсус 3 источников",
            "evidence_strength": "high",
        },
        {
            "label": "Качественные МОПы (lobby/лифты/коридоры)",
            "weight": 22,
            "rationale": "Ценовая премия +8–15% при CAPEX 2–3%, первое что видит покупатель",
            "evidence_strength": "high",
        },
        {
            "label": "Фитнес-центр",
            "weight": 18,
            "rationale": "+3–5% к цене, высокий спрос в целевой аудитории",
            "evidence_strength": "medium",
        },
        {
            "label": "Благоустройство двора / детская площадка",
            "weight": 15,
            "rationale": "Семейная аудитория — основа бизнес-класса",
            "evidence_strength": "high",
        },
        {
            "label": "Консьерж-сервис",
            "weight": 10,
            "rationale": "Дифференциатор, требует операционных расходов",
            "evidence_strength": "medium",
        },
        {
            "label": "Бассейн",
            "weight": 6,
            "rationale": "Имиджевый актив, окупается только в ультра-премиум",
            "evidence_strength": "medium",
        },
        {
            "label": "Сигарная комната / wine room",
            "weight": 4,
            "rationale": "Нишевый спрос, высокий OPEX, окупается редко",
            "evidence_strength": "low",
        },
    ],
    "tables": [
        {
            "title": "Amenities по приоритету и экономике",
            "columns": ["Amenity", "Ценовая премия", "CAPEX доля", "OPEX", "ROI"],
            "rows": [
                ["Закрытая территория", "+7–12%", "0.5–1%", "низкий", "высокий"],
                ["МОПы отель-класса", "+8–15%", "2–3%", "средний", "высокий"],
                ["Фитнес", "+3–5%", "1–2%", "средний", "средний"],
                ["Бассейн", "+2–4%", "3–5%", "высокий", "низкий"],
                ["Сигарная комната", "+1–2%", "0.3–0.5%", "средний", "низкий"],
            ],
            "caption": "Оценка на основе московского рынка бизнес/премиум 2023–2024",
            "source_ref": "Консенсус источников + Analyzer",
        },
        {
            "title": "Ценовые премии по сегментам",
            "columns": ["Сегмент", "Средняя премия", "Диапазон", "Число проектов"],
            "rows": [
                ["Бизнес-класс", "+12%", "8–18%", "47"],
                ["Премиум", "+20%", "15–25%", "23"],
                ["Ультра-премиум", "+28%", "20–35%", "8"],
            ],
            "caption": "Москва 2023–2024, проекты с полным набором amenities",
            "source_ref": "Perplexity + OpenAI DR",
        },
        {
            "title": "CAPEX и OPEX amenities: сравнительная таблица",
            "columns": ["Amenity", "CAPEX (тыс. руб./м² amenity)", "OPEX (тыс. руб./год)", "Порог окупаемости"],
            "rows": [
                ["Фитнес 500 м²", "180–250", "3 500–5 000", "Бизнес-класс 80+ кв."],
                ["Бассейн 25м", "800–1 200", "12 000–18 000", "Премиум 200+ кв."],
                ["МОПы 2000 м²", "120–200", "1 500–2 500", "Бизнес-класс 50+ кв."],
                ["Сигарная 40 м²", "300–450", "800–1 200", "Ультра-премиум 150+ кв."],
            ],
            "caption": "Оценочные данные на основе открытых источников и экспертных интервью",
            "source_ref": "OpenAI DR + отраслевые бенчмарки",
        },
    ],
    "charts": [
        {
            "chart_type": "bar",
            "title": "Ценовая премия от ключевых amenities (бизнес-класс Москва)",
            "data": {
                "labels": ["Закрытая территория", "МОПы отель-класс", "Фитнес", "Бассейн", "Сигарная"],
                "values": [9.5, 11.5, 4.0, 3.0, 1.5],
            },
            "x_label": "Amenity",
            "y_label": "Ценовая премия (%)",
            "caption": "Средние значения диапазонов; источник: консенсус DR-отчётов",
        },
        {
            "chart_type": "stacked_bar",
            "title": "Структура бюджета amenities: CAPEX по категориям",
            "data": {
                "categories": ["Бизнес-класс", "Премиум", "Ультра-премиум"],
                "series": {
                    "МОПы": [2.5, 3.5, 5.0],
                    "Фитнес": [1.5, 2.0, 2.5],
                    "Территория": [0.8, 1.2, 1.5],
                    "Прочее": [0.2, 1.3, 4.0],
                },
            },
            "x_label": "Сегмент",
            "y_label": "% от себестоимости строительства",
            "caption": "CAPEX на amenities как доля от общей сметы",
        },
        {
            "chart_type": "waterfall",
            "title": "ROI на amenities: от CAPEX к ценовой премии",
            "data": {
                "labels": ["Базовая цена", "Закрытая территория", "МОПы", "Фитнес", "Бассейн", "Итого"],
                "values": [100, 9.5, 11.5, 4.0, 3.0, 128.0],
                "types": ["base", "positive", "positive", "positive", "positive", "total"],
            },
            "x_label": "Amenity",
            "y_label": "Индекс цены",
            "caption": "Накопленный эффект amenities на индекс цены квартиры",
        },
    ],
    "callouts": [
        {
            "kind": "insight",
            "title": "Закон убывающей отдачи amenities",
            "body": (
                "После 7–8 amenities каждая следующая добавляет <1% к цене продажи, "
                "но увеличивает операционные расходы на 3–5% в год. "
                "Застройщику выгодно остановиться на «золотом наборе» из 5–7 позиций."
            ),
        },
        {
            "kind": "warning",
            "title": "Бассейн — ловушка для застройщика бизнес-класса",
            "body": (
                "Бассейн требует 3–5% CAPEX при ценовой отдаче +2–4%. "
                "OPEX в 4× выше фитнеса. "
                "Экономически оправдан только в ультра-премиум (>300 тыс. руб./м²)."
            ),
        },
        {
            "kind": "insight",
            "title": "МОПы — самый эффективный рычаг для застройщика",
            "body": (
                "Lobby и коридоры отель-класса дают +8–15% к цене — больше бассейна — "
                "при CAPEX всего 2–3% от сметы. "
                "Это лучшее соотношение инвестиция/премия в категории amenities."
            ),
        },
        {
            "kind": "insight",
            "title": "Сигарные комнаты: имидж без окупаемости",
            "body": (
                "Сигарная комната добавляет +1–2% к цене при OPEX 800–1200 тыс. руб./год. "
                "Срок окупаемости при 100 квартирах — 15+ лет. "
                "Релевантна только как имиджевый элемент ультра-премиум."
            ),
        },
    ],
    "key_numbers_highlight": [
        {
            "value": "+8–15%",
            "label": "ценовая премия от МОПов отель-класса",
            "source_ref": "консенсус DR",
            "importance": "headline",
        },
        {
            "value": "3–5%",
            "label": "оптимальный CAPEX на amenities от себестоимости",
            "source_ref": "Analyzer synthesis",
            "importance": "headline",
        },
        {
            "value": "+7–12%",
            "label": "ценовая премия от закрытой территории",
            "source_ref": "OpenAI DR",
            "importance": "primary",
        },
        {
            "value": "5–7",
            "label": "оптимальное число amenities для бизнес-класса",
            "source_ref": "Perplexity",
            "importance": "primary",
        },
        {
            "value": "4×",
            "label": "OPEX бассейна vs фитнеса",
            "source_ref": "industry benchmark",
            "importance": "secondary",
        },
        {
            "value": "+18%",
            "label": "максимальная ценовая премия full-amenity бизнес-класс",
            "source_ref": "OpenAI DR",
            "importance": "primary",
        },
    ],
    "cover_image_prompt": None,
}


def _make_session() -> V4Session:
    """Create a V4Session with the amenities question and minimal analysis."""
    return V4Session(
        session_id="night-test-01",
        raw_question=AMENITIES_QUESTION,
        research_prompt=ResearchPrompt(
            full_prompt="Research Moscow business/premium newbuild amenities 2024.",
            reasoning="Amenities ROI analysis",
        ),
        source_reports=[
            UploadedMarkdown(
                filename="deep-research-report-1.md",
                content="# DR Report 1\nMoscow amenities analysis...",
                detected_tool="openai_dr",
            ),
            UploadedMarkdown(
                filename="deep-research-report-2.md",
                content="# DR Report 2\nPremium amenities study...",
                detected_tool="perplexity",
            ),
            UploadedMarkdown(
                filename="amenities-main.md",
                content="# Main amenities data\nDetailed amenities tables...",
                detected_tool="claude",
            ),
            UploadedMarkdown(
                filename="amenities-methodology.md",
                content="# Methodology\nData collection approach...",
                detected_tool="other",
            ),
        ],
        analysis=AnalysisOutput(
            consensus=[
                ConsensusClaim(
                    claim="Закрытая территория — наиболее востребованная amenity",
                    supporting_sources=["openai_dr", "perplexity", "claude"],
                    confidence="high",
                )
            ],
        ),
        status="analyzed",
        created_at=datetime(2026, 4, 18, 0, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_structured_llm(monkeypatch):
    """Monkeypatch LLM to return structured mock JSON."""

    async def _stub(*args, **kwargs):
        return LLMResult(text=json.dumps(_MOCK_STRUCTURED_JSON, ensure_ascii=False), cost_rub=0.0)

    monkeypatch.setattr(synth_module, "call_json", _stub)


# ---------------------------------------------------------------------------
# Core integration test: synthesizer returns populated FinalReport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesizer_returns_structured_final_report(mock_structured_llm):
    """Synthesizer with new prompt returns FinalReport with all structured fields."""
    session = _make_session()
    final, _ = await synthesize_final_report(session)

    assert isinstance(final, FinalReport)
    assert final.session_id == "night-test-01"  # session_id overrides LLM echo


# ---------------------------------------------------------------------------
# DoD threshold tests per spec §4.A.4
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qa_section_has_minimum_4_items(mock_structured_llm):
    """qa_section must have at least 4 items (DoD)."""
    final, _ = await synthesize_final_report(_make_session())
    assert len(final.qa_section) >= 4, (
        f"qa_section has {len(final.qa_section)} items, DoD requires >= 4"
    )


@pytest.mark.asyncio
async def test_qa_section_covers_all_5_sub_questions(mock_structured_llm):
    """qa_section must cover all 5 sub-questions from the amenities request."""
    final, _ = await synthesize_final_report(_make_session())

    # The 5 sub-questions from spec §3
    expected_keywords = [
        # Q1: what's in demand vs not
        ["спросом", "пользуется"],
        # Q2: which parameters are needed
        ["параметры", "нужны"],
        # Q3: price premium / willingness to pay
        ["платить", "премия"],
        # Q4: optimal assortment balance
        ["баланс", "ассортимент"],
        # Q5: economic balance for developer
        ["экономич", "застройщик"],
    ]

    qa_texts = [
        (item.question + " " + item.answer).lower()
        for item in final.qa_section
    ]

    for i, keywords in enumerate(expected_keywords, start=1):
        found = any(
            all(kw.lower() in qa_text for kw in keywords)
            for qa_text in qa_texts
        )
        assert found, (
            f"Sub-question {i} (keywords={keywords}) not covered in qa_section. "
            f"Got: {[item.question for item in final.qa_section]}"
        )


@pytest.mark.asyncio
async def test_tables_has_minimum_3(mock_structured_llm):
    """tables must have at least 3 Table objects (DoD)."""
    final, _ = await synthesize_final_report(_make_session())
    assert len(final.tables) >= 3, (
        f"tables has {len(final.tables)} items, DoD requires >= 3"
    )


@pytest.mark.asyncio
async def test_charts_has_minimum_3(mock_structured_llm):
    """charts must have at least 3 ChartSpec objects (DoD)."""
    final, _ = await synthesize_final_report(_make_session())
    assert len(final.charts) >= 3, (
        f"charts has {len(final.charts)} items, DoD requires >= 3"
    )


@pytest.mark.asyncio
async def test_callouts_has_minimum_3(mock_structured_llm):
    """callouts must have at least 3 CalloutBlock objects (DoD)."""
    final, _ = await synthesize_final_report(_make_session())
    assert len(final.callouts) >= 3, (
        f"callouts has {len(final.callouts)} items, DoD requires >= 3"
    )


@pytest.mark.asyncio
async def test_key_numbers_highlight_between_5_and_7(mock_structured_llm):
    """key_numbers_highlight must have 5–7 items (DoD)."""
    final, _ = await synthesize_final_report(_make_session())
    assert 5 <= len(final.key_numbers_highlight) <= 7, (
        f"key_numbers_highlight has {len(final.key_numbers_highlight)} items, DoD requires 5–7"
    )


@pytest.mark.asyncio
async def test_ranking_structured_with_weights(mock_structured_llm):
    """ranking must be structured and have weight values (DoD)."""
    final, _ = await synthesize_final_report(_make_session())
    assert len(final.ranking) > 0, "ranking must not be empty"
    items_with_weight = [r for r in final.ranking if r.weight is not None]
    assert len(items_with_weight) > 0, "At least some ranking items must have weight"


# ---------------------------------------------------------------------------
# Type validation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qa_section_items_are_qa_item_instances(mock_structured_llm):
    """Each element of qa_section is a QAItem with non-empty fields."""
    final, _ = await synthesize_final_report(_make_session())
    for item in final.qa_section:
        assert isinstance(item, QAItem)
        assert item.question
        assert item.answer


@pytest.mark.asyncio
async def test_ranking_items_are_ranking_item_instances(mock_structured_llm):
    """Each element of ranking is a RankingItem with valid evidence_strength."""
    final, _ = await synthesize_final_report(_make_session())
    valid_strengths = {"high", "medium", "low"}
    for item in final.ranking:
        assert isinstance(item, RankingItem)
        assert item.label
        assert item.evidence_strength in valid_strengths


@pytest.mark.asyncio
async def test_tables_have_valid_structure(mock_structured_llm):
    """Each Table has title, columns and rows that match column count."""
    final, _ = await synthesize_final_report(_make_session())
    for tbl in final.tables:
        assert isinstance(tbl, Table)
        assert tbl.title
        assert len(tbl.columns) > 0
        for row in tbl.rows:
            assert len(row) == len(tbl.columns), (
                f"Table '{tbl.title}': row length {len(row)} != column count {len(tbl.columns)}"
            )


@pytest.mark.asyncio
async def test_charts_have_valid_type_and_data(mock_structured_llm):
    """Each ChartSpec has a valid chart_type and non-empty data dict."""
    valid_types = {"bar", "line", "pie", "scatter", "stacked_bar", "waterfall"}
    final, _ = await synthesize_final_report(_make_session())
    for chart in final.charts:
        assert isinstance(chart, ChartSpec)
        assert chart.chart_type in valid_types
        assert chart.title
        assert isinstance(chart.data, dict)
        assert len(chart.data) > 0


@pytest.mark.asyncio
async def test_callouts_have_valid_kind(mock_structured_llm):
    """Each CalloutBlock has a valid kind."""
    valid_kinds = {"insight", "warning", "key_number", "note"}
    final, _ = await synthesize_final_report(_make_session())
    for callout in final.callouts:
        assert isinstance(callout, CalloutBlock)
        assert callout.kind in valid_kinds
        assert callout.title
        assert callout.body


@pytest.mark.asyncio
async def test_key_numbers_highlight_have_valid_importance(mock_structured_llm):
    """Each KeyNumberHighlight has a valid importance level."""
    valid_importance = {"headline", "primary", "secondary"}
    final, _ = await synthesize_final_report(_make_session())
    for kn in final.key_numbers_highlight:
        assert isinstance(kn, KeyNumberHighlight)
        assert kn.value
        assert kn.label
        assert kn.importance in valid_importance


# ---------------------------------------------------------------------------
# Backward compatibility test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_fields_still_work(mock_structured_llm):
    """Existing FinalReport fields are still populated correctly."""
    session = _make_session()
    final, _ = await synthesize_final_report(session)

    # Existing fields must still work
    assert final.session_id == session.session_id
    assert final.question  # raw_question or LLM echo
    assert final.executive_summary.main_answer
    assert len(final.executive_summary.top_findings) > 0
    assert len(final.executive_summary.key_numbers) > 0
    assert len(final.all_sources) > 0
    assert isinstance(final.metadata, dict)


# ---------------------------------------------------------------------------
# Coercer unit tests (test helpers directly)
# ---------------------------------------------------------------------------


def test_coerce_qa_section_valid():
    raw = [
        {"question": "Q1?", "answer": "A1.", "details_ref": "Section 1"},
        {"question": "Q2?", "answer": "A2.", "details_ref": ""},
    ]
    result = _coerce_qa_section(raw)
    assert len(result) == 2
    assert result[0].question == "Q1?"
    assert result[1].details_ref == ""


def test_coerce_qa_section_skips_incomplete():
    raw = [
        {"question": "Q1?", "answer": ""},  # empty answer → skipped
        {"question": "", "answer": "A2."},  # empty question → skipped
        {"question": "Q3?", "answer": "A3."},  # valid
    ]
    result = _coerce_qa_section(raw)
    assert len(result) == 1
    assert result[0].question == "Q3?"


def test_coerce_qa_section_handles_non_list():
    assert _coerce_qa_section(None) == []
    assert _coerce_qa_section("string") == []
    assert _coerce_qa_section(42) == []


def test_coerce_ranking_valid():
    raw = [
        {"label": "Item A", "weight": 45, "rationale": "strong", "evidence_strength": "high"},
        {"label": "Item B", "weight": None, "rationale": "weak", "evidence_strength": "low"},
        {"label": "Item C", "rationale": "medium"},  # no weight, no strength → defaults
    ]
    result = _coerce_ranking(raw)
    assert len(result) == 3
    assert result[0].weight == 45
    assert result[1].weight is None
    assert result[2].evidence_strength == "medium"  # default


def test_coerce_ranking_skips_missing_label():
    raw = [
        {"label": "", "weight": 10, "rationale": "x", "evidence_strength": "high"},
        {"weight": 10, "rationale": "x"},  # no label key
    ]
    result = _coerce_ranking(raw)
    assert len(result) == 0


def test_coerce_ranking_float_weight_converted_to_int():
    raw = [{"label": "A", "weight": 30.7, "rationale": "x", "evidence_strength": "high"}]
    result = _coerce_ranking(raw)
    assert result[0].weight == 30
    assert isinstance(result[0].weight, int)


def test_coerce_tables_valid():
    raw = [
        {
            "title": "T1",
            "columns": ["A", "B"],
            "rows": [["a1", "b1"], ["a2", "b2"]],
            "caption": "cap",
            "source_ref": "src",
        }
    ]
    result = _coerce_tables(raw)
    assert len(result) == 1
    assert result[0].title == "T1"
    assert result[0].columns == ["A", "B"]
    assert len(result[0].rows) == 2
    assert result[0].caption == "cap"


def test_coerce_tables_skips_missing_title_or_columns():
    raw = [
        {"title": "", "columns": ["A"], "rows": []},
        {"title": "T", "columns": [], "rows": []},
        {"title": "T2", "columns": ["X"], "rows": [["v"]]},
    ]
    result = _coerce_tables(raw)
    assert len(result) == 1
    assert result[0].title == "T2"


def test_coerce_charts_valid():
    raw = [
        {
            "chart_type": "bar",
            "title": "Bar Chart",
            "data": {"labels": ["A", "B"], "values": [1, 2]},
            "x_label": "X",
            "y_label": "Y",
        }
    ]
    result = _coerce_charts(raw)
    assert len(result) == 1
    assert result[0].chart_type == "bar"
    assert result[0].x_label == "X"


def test_coerce_charts_skips_invalid_type():
    raw = [
        {"chart_type": "unknown_type", "title": "X", "data": {}},
        {"chart_type": "line", "title": "L", "data": {"x": [1], "y": [2]}},
    ]
    result = _coerce_charts(raw)
    assert len(result) == 1
    assert result[0].chart_type == "line"


def test_coerce_charts_skips_missing_data():
    raw = [
        {"chart_type": "bar", "title": "No data"},  # missing data key
        {"chart_type": "bar", "title": "With data", "data": {"v": [1]}},
    ]
    result = _coerce_charts(raw)
    assert len(result) == 1


def test_coerce_callouts_valid():
    raw = [
        {"kind": "insight", "title": "Title", "body": "Body text."},
        {"kind": "warning", "title": "Risk", "body": "Risk description."},
    ]
    result = _coerce_callouts(raw)
    assert len(result) == 2
    assert result[0].kind == "insight"
    assert result[1].kind == "warning"


def test_coerce_callouts_skips_invalid_kind():
    raw = [
        {"kind": "invalid_kind", "title": "T", "body": "B"},
        {"kind": "note", "title": "T2", "body": "B2"},
    ]
    result = _coerce_callouts(raw)
    assert len(result) == 1
    assert result[0].kind == "note"


def test_coerce_callouts_skips_empty_body():
    raw = [
        {"kind": "insight", "title": "T", "body": ""},
        {"kind": "insight", "title": "T2", "body": "Valid body."},
    ]
    result = _coerce_callouts(raw)
    assert len(result) == 1


def test_coerce_key_numbers_highlight_valid():
    raw = [
        {"value": "+12%", "label": "price premium", "source_ref": "ERZ", "importance": "headline"},
        {"value": "3–5%", "label": "capex share", "source_ref": "analysis", "importance": "primary"},
    ]
    result = _coerce_key_numbers_highlight(raw)
    assert len(result) == 2
    assert result[0].importance == "headline"
    assert result[1].importance == "primary"


def test_coerce_key_numbers_highlight_skips_missing_value_or_label():
    raw = [
        {"value": "", "label": "label", "source_ref": "src", "importance": "headline"},
        {"value": "10%", "label": "", "source_ref": "src", "importance": "headline"},
        {"value": "5%", "label": "valid", "source_ref": "src", "importance": "secondary"},
    ]
    result = _coerce_key_numbers_highlight(raw)
    assert len(result) == 1
    assert result[0].value == "5%"


def test_coerce_key_numbers_highlight_defaults_invalid_importance():
    raw = [
        {"value": "X", "label": "Y", "source_ref": "Z", "importance": "ultra_super"},
    ]
    result = _coerce_key_numbers_highlight(raw)
    assert len(result) == 1
    assert result[0].importance == "primary"  # default


# ---------------------------------------------------------------------------
# FinalReport backward-compat: empty new fields don't break old tests
# ---------------------------------------------------------------------------


def test_final_report_new_fields_default_to_empty():
    """New fields all default to empty — no breakage for legacy code."""
    from smart_report.models import ExecutiveSummaryV4

    report = FinalReport(
        session_id="s",
        question="q",
        executive_summary=ExecutiveSummaryV4(
            main_answer="a",
            top_findings=[],
            key_numbers=[],
            confidence_note="",
            what_meta_adds="",
        ),
    )
    assert report.qa_section == []
    assert report.ranking == []
    assert report.tables == []
    assert report.charts == []
    assert report.callouts == []
    assert report.key_numbers_highlight == []
    assert report.cover_image_prompt is None


# ---------------------------------------------------------------------------
# Schema serialization round-trip test
# ---------------------------------------------------------------------------


def test_final_report_serializes_new_fields():
    """New fields appear correctly in model_dump() output."""
    from smart_report.models import ExecutiveSummaryV4

    report = FinalReport(
        session_id="s",
        question="q",
        executive_summary=ExecutiveSummaryV4(
            main_answer="a",
            top_findings=[],
            key_numbers=[],
            confidence_note="",
            what_meta_adds="",
        ),
        qa_section=[QAItem(question="Q?", answer="A.", details_ref="sec1")],
        ranking=[RankingItem(label="X", weight=50, rationale="r", evidence_strength="high")],
        tables=[Table(title="T", columns=["A", "B"], rows=[["1", "2"]])],
        charts=[ChartSpec(chart_type="bar", title="C", data={"v": [1]})],
        callouts=[CalloutBlock(kind="insight", title="I", body="b")],
        key_numbers_highlight=[
            KeyNumberHighlight(value="5%", label="l", source_ref="src", importance="headline")
        ],
    )

    d = report.model_dump()
    assert len(d["qa_section"]) == 1
    assert d["qa_section"][0]["question"] == "Q?"
    assert len(d["ranking"]) == 1
    assert d["ranking"][0]["weight"] == 50
    assert len(d["tables"]) == 1
    assert len(d["charts"]) == 1
    assert d["charts"][0]["chart_type"] == "bar"
    assert len(d["callouts"]) == 1
    assert len(d["key_numbers_highlight"]) == 1
    assert d["key_numbers_highlight"][0]["importance"] == "headline"
