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


# ---------------------------------------------------------------------------
# v4.5 Phase 2 Step 2.2 — broad strategic detector (LLM-planner gate)
# ---------------------------------------------------------------------------
# Used by Prompt Master to decide between three paths:
#   1. is_russian_re_strategic → fixed RU RE template (Step 2.1, free)
#   2. is_strategic_query      → LLM planner (Step 2.2, ~$0.05-0.10)
#   3. neither                 → no decomposition, single-pass
# Note: is_russian_re_strategic ⊂ is_strategic_query for any RU RE
# strategic query, so the order in the router matters. Domain template
# wins on RU RE because it's cheaper (no LLM call) and pre-validated.

_BROAD_STRATEGIC_MARKERS: tuple[str, ...] = (
    # Russian markers — superset of _STRATEGIC_MARKERS with synonyms
    "тренд",
    "влияет",
    "влияют",
    "влияни",
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
    "анализ",
    "оцени",
    "оценка",
    "сценари",
    "как ",
    "повлия",
    # English markers — for future bilingual / non-RU queries
    "trend",
    "impact",
    "forecast",
    "risk",
    "recommend",
    "strategic",
    "analyze",
    "analysis",
    "compare",
    "comparison",
    "evaluate",
    "evaluation",
    "scenario",
    "outlook",
    "drivers",
    "rationale",
    # v4.5 Phase 3 Step 3.1 — regulatory/policy markers (Run 1 finding 1).
    # Q3 EU DAC ("How is Direct Air Capture regulated in the EU and
    # what subsidies are available in 2026?") missed every existing
    # marker and routed to "none" instead of llm_planner — silently
    # dropping the planner stage on every regulatory/policy query.
    # RU regulatory/policy
    "регулируется",
    "регулирование",
    "регуляторик",
    "норматив",
    "требовани",
    "субсиди",
    "льгот",
    "программа",
    "законодательств",
    "политика",
    "реформа",
    "стандарт",
    # EN regulatory/policy
    "regulated",
    "regulation",
    "regulatory",
    "policy",
    "framework",
    "landscape",
    "subsidies",
    "subsidy",
    "available",
    "requirements",
    "comply",
    "compliance",
    "standards",
    "certification",
    "directive",
)

# Length gate: tuned against the Step 2.2 spec acceptance examples.
# The spec text suggested >=12 but its own positive examples sit at
# 7-9 words ("Compare LLM observability platforms ... for enterprise
# scale" = 7 tokens; "Какие тренды повлияют на девелоперов в Москве в
# 2026-2027?" = 9 tokens). 7 satisfies all positive cases while still
# rejecting truly short strategic-sounding lookups ("Выбор ипотеки
# или аренды?" = 4) where decomposition adds no value.
_STRATEGIC_MIN_WORDS = 7


def is_strategic_query(query: str) -> bool:
    """Return True for queries that warrant decomposition (template or LLM).

    Two conditions must both hold:
      - At least one strategic marker present (analytical-intent signal)
      - At least 7 words long (rules out short factual lookups like
        "какая ставка ЦБ?" even if they contain "what")

    Both gates necessary: long descriptive queries without strategic
    markers (e.g. "Опиши историю развития ЖК Прайм Парк за 5 лет с
    инфраструктурой и парковкой") are factual and don't need
    decomposition; short strategic-sounding queries ("выбор ипотеки?")
    are too vague for sub-questions to add value.
    """
    if not query or not query.strip():
        return False
    q_lower = query.lower()
    has_marker = any(m in q_lower for m in _BROAD_STRATEGIC_MARKERS)
    if not has_marker:
        return False
    word_count = len(query.split())
    return word_count >= _STRATEGIC_MIN_WORDS


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


# ---------------------------------------------------------------------------
# v4.5 Phase 2 Step 2.2 — LLM-driven planner (C2 full)
# ---------------------------------------------------------------------------
# When a query is strategic but does NOT match a known domain template,
# we let an LLM decompose it into 3-5 sub-questions with dependency
# tracking. Default model is Haiku 4.5 — at ~200 tokens of system
# prompt and ~500 tokens of output, one call costs $0.005-0.02 (well
# under the $0.05-0.10 spec target).
#
# The planner is intentionally model-agnostic and stateless: pass any
# OpenRouter model id, get back a list of SubQuestion. Failures (HTTP
# error, malformed JSON) return an empty list rather than raising —
# the orchestrator falls back to no-decomposition with the
# decomposition_method = "llm_planner_failed" tag for observability.

import json as _json_planner
import logging as _logging_planner

from .io import extract_json as _extract_json
from .llm import call_json
from .models import SubQuestion as _SubQuestion

_planner_log = _logging_planner.getLogger(__name__)


# Haiku 4.5 default — verified Cheap-tier viable in Run 2.
DEFAULT_PLANNER_MODEL = "anthropic/claude-haiku-4.5"


PLANNER_SYSTEM_PROMPT = """You are a research analyst decomposing a strategic question into atomic, independently retrievable sub-questions.

Rules:
- Generate 3-5 sub-questions. Fewer than 3 means the parent query was not strategic enough; more than 5 fragments the analysis.
- Each sub-question must be specific and answerable by a research tool (Perplexity / OpenAI DR / Claude Research).
- Track dependencies. If sub-question N's framing or interpretation requires the answer to sub-question M, set depends_on=["sqM"] for N. Most decompositions have 0-2 dependencies; a fully linear chain of 5 dependencies is a smell.
- Provide a one-sentence rationale for each sub-question — what slice of the analytical surface it covers.
- Provide suggested_sources as 1-4 source-type hints ("regulatory", "market_data", "academic", "industry_report", "vendor_docs", "news", "case_study", "expert_interview"). Use generic types, not specific publishers.
- Stay in the language of the input query (Russian → Russian sub-questions, English → English).

Anti-patterns:
- Restating the original query as one sub-question
- Vague meta-questions ("what should we consider?", "what are the implications?")
- Overlapping sub-questions that retrieve the same evidence
- More than 2 sub-questions sharing the same suggested_sources

Output STRICT JSON matching this schema. No prose outside JSON. No markdown fences.

{
  "sub_questions": [
    {
      "id": "sq1",
      "text": "...",
      "depends_on": [],
      "rationale": "...",
      "suggested_sources": ["regulatory", "industry_report"]
    },
    {
      "id": "sq2",
      "text": "...",
      "depends_on": ["sq1"],
      "rationale": "...",
      "suggested_sources": ["market_data"]
    }
  ]
}
"""


async def generate_sub_questions(
    query: str,
    *,
    model: str = DEFAULT_PLANNER_MODEL,
    max_sub_questions: int = 5,
    mock: bool = False,
) -> list[_SubQuestion]:
    """Decompose *query* into 3-5 SubQuestion objects via an LLM call.

    Returns an empty list on any failure (HTTP error, malformed JSON,
    schema-invalid output). Callers should treat empty as "fall back to
    no-decomposition" and log via decomposition_method tag — never crash
    the pipeline because the planner had a bad day.

    Pass ``mock=True`` for unit tests; returns an empty list without
    touching the network or LLM module.
    """
    if not query or not query.strip():
        return []
    if mock:
        return []

    user_message = (
        f"Strategic query to decompose:\n{query.strip()}\n\n"
        f"Generate at most {max_sub_questions} sub-questions following the "
        f"system prompt rules. Return only the JSON object."
    )

    try:
        result = await call_json(
            role="planner",
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            max_tokens=2000,
        )
    except Exception as e:  # pragma: no cover — network/HTTP edge
        _planner_log.warning("planner LLM call failed: %r — returning empty", e)
        return []

    return _parse_planner_output(result.text, cap=max_sub_questions)


def _parse_planner_output(raw: str, *, cap: int) -> list[_SubQuestion]:
    """Convert raw planner JSON into validated SubQuestion list.

    Uses io.extract_json so markdown ```json fences (Haiku 4.5 wraps
    its JSON output in fences despite response_format hint) and minor
    LLM JSON glitches (trailing commas, unescaped quotes) are tolerated.
    Failure → empty list, never crash.
    """
    try:
        data = _extract_json(raw)
    except (ValueError, _json_planner.JSONDecodeError) as e:
        _planner_log.warning("planner JSON parse failed: %r", e)
        return []
    if not isinstance(data, dict):
        return []
    raw_items = data.get("sub_questions")
    if not isinstance(raw_items, list):
        return []

    sub_qs: list[_SubQuestion] = []
    for item in raw_items[:cap]:
        if not isinstance(item, dict):
            continue
        try:
            sq = _SubQuestion(
                id=str(item.get("id") or f"sq{len(sub_qs) + 1}"),
                text=str(item.get("text") or "").strip(),
                depends_on=[
                    str(d) for d in (item.get("depends_on") or []) if isinstance(d, str)
                ],
                rationale=str(item.get("rationale") or "").strip(),
                suggested_sources=[
                    str(s) for s in (item.get("suggested_sources") or []) if isinstance(s, str)
                ],
            )
        except Exception as e:  # pydantic validation
            _planner_log.warning("planner sub-question rejected: %r — %r", item, e)
            continue
        if not sq.text:
            continue  # skip empty-text items
        sub_qs.append(sq)
    return sub_qs


def format_planner_guidance(sub_questions: list[_SubQuestion]) -> str:
    """Render LLM-planner sub-questions as a Markdown addendum for the analyst.

    Mirrors format_template_guidance in shape so downstream readers
    (analyst UI, frontend) can treat both decomposition methods
    uniformly. Returns empty string for empty input.

    Pure-Cyrillic body intentionally — same anti-lint-retry discipline
    as the v4.5 metadata warning. Sub-question text itself comes from
    the LLM and may contain Latin tokens; that's expected and not
    counted against the lint threshold (full_prompt is not lint-scanned).
    """
    if not sub_questions:
        return ""

    lines = [
        "",
        "---",
        "",
        f"## Декомпозиция запроса (planner LLM, {len(sub_questions)} sub-questions)",
        "",
        (
            "Этот запрос распознан как стратегический, но не подходит ни под "
            "один доменный шаблон. Планировщик разложил его на под-вопросы — "
            "прогони каждый отдельно в DR-инструменте и загрузи отчёты обратно. "
            "Зависимости между под-вопросами обозначены: вопросы с непустым "
            "`depends_on` лучше прогонять после своих зависимостей."
        ),
        "",
    ]
    for sq in sub_questions:
        lines.append(f"### `{sq.id}` — {sq.text}")
        lines.append("")
        if sq.rationale:
            lines.append(f"_Зачем:_ {sq.rationale}")
            lines.append("")
        if sq.depends_on:
            deps = ", ".join(f"`{d}`" for d in sq.depends_on)
            lines.append(f"_Зависит от:_ {deps}")
            lines.append("")
        if sq.suggested_sources:
            sources_csv = ", ".join(sq.suggested_sources)
            lines.append(f"_Тип источников:_ {sources_csv}")
            lines.append("")

    return "\n".join(lines)
