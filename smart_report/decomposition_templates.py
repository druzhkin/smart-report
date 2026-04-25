"""Domain-specific decomposition templates (v4.5 Phase 2 Step 2.1).

When a query is recognised as a "strategic Russian real-estate" question
(Cyrillic + RE-vocabulary + a strategic marker like тренд / прогноз /
рекоменд), the pipeline can decompose it into a fixed set of four
sub-questions covering macro, regulation, market data, and developer
behaviour, each with a curated source-priority list.

This is the K-Dense "domain template" pattern: instead of asking the
LLM to invent a decomposition (which on Russian RE topics tends to
collapse into one wide query that misses regulatory drivers), we hand
it a structurally complete set of probes with their authoritative
sources spelled out.

The integration point in v4 is the Prompt Master: the generated
ResearchPrompt is augmented with a guidance addendum so the analyst
runs four targeted DR queries rather than one broad one. No LLM call
is added; no auto-retrieval is wired (that's Roadmap Phase 3).
"""

from __future__ import annotations

import re
from typing import TypedDict


# ---------------------------------------------------------------------------
# Template structure
# ---------------------------------------------------------------------------


class SubQuery(TypedDict):
    """One slot in a decomposition template."""

    id: str
    prompt: str
    sources_priority: list[str]


# ---------------------------------------------------------------------------
# Russian RE strategic template — 4 sub-questions
# ---------------------------------------------------------------------------
# Numbers reasoning:
#   4 sub-questions covers the K-Dense "macro / regulation / market /
#   actor-behaviour" frame for any segment of the Russian housing stack.
#   The 5th candidate from earlier drafts ("buyer financing") collapses
#   into macro_context (key rate + mortgage policy) and market_data
#   (mortgage share by segment), so it stays merged.

RUSSIAN_RE_STRATEGIC_TEMPLATE: dict[str, SubQuery] = {
    "macro_context": {
        "id": "macro_context",
        "prompt": (
            "Что происходит в российской макроэкономике, что напрямую "
            "влияет на жилищное строительство и спрос: ключевая ставка ЦБ "
            "и её траектория, инфляция и ИПЦ строительства Росстата, ВВП, "
            "реальные располагаемые доходы населения, ипотечный рынок "
            "(объёмы, ставки, господдержка). Дай конкретные числа за "
            "последние 4 квартала и базовый прогноз ЦБ на следующий год."
        ),
        "sources_priority": [
            "cbr.ru",
            "rosstat.gov.ru",
            "minfin.gov.ru",
            "дом.рф",
        ],
    },
    "regulatory_environment": {
        "id": "regulatory_environment",
        "prompt": (
            "Какие регуляторные изменения за последние 12 месяцев и "
            "ожидаемые в ближайшие 12 месяцев влияют на бизнес-сегмент "
            "жилищного строительства: изменения в 214-ФЗ, эскроу-счета, "
            "проектное финансирование, программы господдержки ипотеки, "
            "нормативы Минстроя, налоговые изменения. Цитируй конкретные "
            "акты с датой принятия и точкой вступления в силу."
        ),
        "sources_priority": [
            "minstroyrf.gov.ru",
            "дом.рф",
            "publication.pravo.gov.ru",
            "pravo.gov.ru",
            "cbr.ru",
        ],
    },
    "market_data": {
        "id": "market_data",
        "prompt": (
            "Текущее состояние московского рынка жилья по бизнес-сегменту: "
            "цены за м² по локациям, объёмы продаж и запусков, структура "
            "спроса, доля ипотечных сделок, сроки экспозиции, скидки. "
            "Сопоставь данные ДОМ.РФ ЕИСЖС, Росстата по строительству и "
            "топ-консалтингов (Knight Frank, JLL, CBRE, NF Group, Nikoliers, "
            "Metrium). При расхождениях фиксируй обе цифры с источниками."
        ),
        "sources_priority": [
            "дом.рф",
            "rosstat.gov.ru",
            "erzrf.ru",
            "knightfrank.ru",
            "jllrussia.com",
            "cbre.ru",
            "nfgroup.ru",
            "metrium.ru",
        ],
    },
    "developer_behavior": {
        "id": "developer_behavior",
        "prompt": (
            "Поведение крупных девелоперов бизнес-сегмента в Москве за "
            "последние 12 месяцев: пайплайн новых проектов, динамика "
            "ленд-банков, M&A и партнёрства, публичные заявления "
            "топ-менеджмента, корпоративные действия (IPO, размещения "
            "облигаций). Имена и данные по топ-10 застройщиков сегмента "
            "по ЕРЗ. Источники: ЕГРЮЛ, ЕРЗ, корпоративные пресс-релизы, "
            "деловая пресса."
        ),
        "sources_priority": [
            "erzrf.ru",
            "egrul.nalog.ru",
            "kommersant.ru",
            "rbc.ru",
            "vedomosti.ru",
            "interfax.ru",
        ],
    },
}


# ---------------------------------------------------------------------------
# Heuristic — does this query warrant the Russian RE strategic template?
# ---------------------------------------------------------------------------
# All three signals must fire:
#   1. Cyrillic chars (filters out English-only queries)
#   2. RE-vocabulary keyword (filters out non-RE Russian queries)
#   3. Strategic marker (filters out simple factual lookups like
#      "какая ипотечная ставка сегодня")
# Two-out-of-three would over-trigger the template on, e.g., factual
# RE questions ("сколько стоит квадратный метр в ЖК X").

_RE_CYRILLIC = re.compile(r"[а-яА-Я]")

_RE_KEYWORDS: tuple[str, ...] = (
    "девелопер",
    "застройщик",
    "жилья",
    "жильё",
    "жилое",
    "жилищн",
    "жк ",
    "новостр",
    "апартамент",
    "недвижимост",
    "строительств",
    "ипотек",
    "бизнес-класс",
    "бизнес класс",
    "премиум-класс",
    "элит",
    "первичк",
    "вторичк",
    "квартир",
)

_STRATEGIC_MARKERS: tuple[str, ...] = (
    "тренд",
    "влияет",
    "влияют",
    "перспектив",
    "прогноз",
    "риск",
    "рекоменд",
    "лидир",
    "стратег",
    "успех",
    "выбор",
    "сравн",
    "оптимальн",
    "приоритет",
    "что определяет",
    "что движет",
    "почему",
)


def is_russian_re_strategic(query: str) -> bool:
    """Return True when *query* should be decomposed via the RU RE template."""
    if not query:
        return False
    has_cyrillic = bool(_RE_CYRILLIC.search(query))
    if not has_cyrillic:
        return False

    q_lower = query.lower()
    has_re = any(kw in q_lower for kw in _RE_KEYWORDS)
    has_strategic = any(marker in q_lower for marker in _STRATEGIC_MARKERS)
    return has_re and has_strategic


def decompose(query: str) -> list[SubQuery]:
    """Return the decomposition for *query*, or an empty list when no template fits.

    The current registry has exactly one template (Russian RE strategic);
    when that doesn't match, callers fall back to the LLM's own
    decomposition. Adding more templates later means extending this
    routing without changing call sites.
    """
    if is_russian_re_strategic(query):
        return list(RUSSIAN_RE_STRATEGIC_TEMPLATE.values())
    return []


# ---------------------------------------------------------------------------
# Guidance text for inclusion in Prompt Master output
# ---------------------------------------------------------------------------


def format_template_guidance(sub_queries: list[SubQuery]) -> str:
    """Render *sub_queries* as a Markdown addendum for the analyst.

    Returns an empty string when *sub_queries* is empty so callers can
    unconditionally append the result. The text is pure Cyrillic
    apart from domain names — those are URLs, which the language linter
    strips before scanning, so they don't add to the warning count.
    """
    if not sub_queries:
        return ""

    lines = [
        "",
        "---",
        "",
        "## Декомпозиция запроса (template Russian-RE-strategic)",
        "",
        (
            "Этот запрос распознан как стратегический по рынку российской "
            "недвижимости. Вместо одного широкого запроса прогони "
            f"{len(sub_queries)} целевых под-запроса в DR-инструменте — каждый "
            "со своим приоритетом источников. Это даёт более глубокое "
            "покрытие и автоматически распределяет evidence по "
            "ключевым векторам анализа."
        ),
        "",
    ]
    for i, sq in enumerate(sub_queries, start=1):
        lines.append(f"### Под-запрос {i} — `{sq['id']}`")
        lines.append("")
        lines.append(sq["prompt"])
        lines.append("")
        priority_csv = ", ".join(sq["sources_priority"])
        lines.append(f"**Приоритет источников:** {priority_csv}")
        lines.append("")

    lines.append(
        "**Сводка:** прогони каждый под-запрос отдельно в выбранном "
        "DR-инструменте, загрузи получившиеся отчёты обратно в систему. "
        "Аналитический слой сопоставит ответы и синтезирует."
    )
    lines.append("")

    return "\n".join(lines)
