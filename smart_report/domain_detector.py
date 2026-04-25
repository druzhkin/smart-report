"""Heuristic query-domain detector (v4.5 Phase 3 Step 3.2).

Comparison Run 1 showed the global RU-RE-only authoritative registry
is the wrong shape for any non-RU-RE query: Q1 EV needed Автостат /
АЕБ / Минпромторг, Q3 EU DAC needed europa.eu / cinea.ec.europa.eu.
Step 3.1 unioned the EU regulatory tier into the global registry as a
hot-fix; Step 3.2 introduces the proper structure — a small enum of
known query domains, a heuristic detector that maps a query to one,
and a per-domain authoritative registry consumed by gap_detector and
synthesizer.

Design choices:
  - Heuristic, not LLM: every domain detection is free + deterministic.
    If accuracy proves insufficient on real queries we fall back to an
    LLM stage in Phase 4 — for now the cost-of-mistake (one slightly
    misweighted gap signal) is small.
  - Order of checks goes most-specific to fall-through GENERIC.
    RU + RE-vocab beats RU + automotive in the rare case both fire,
    since RU RE is our flagship domain.
  - Markers are lowercase substrings to match _BROAD_STRATEGIC_MARKERS
    style. Same regex tokenizer as gap_detector applies in callers.
"""

from __future__ import annotations

import re
from enum import Enum


class QueryDomain(str, Enum):
    """Recognised query-topic domains for routing authoritative-source lookup.

    Inherits from str so JSON serialisation stays human-readable.
    """

    RU_REAL_ESTATE = "ru_real_estate"
    RU_AUTOMOTIVE = "ru_automotive"
    RU_TECH_SAAS = "ru_tech_saas"
    EU_REGULATORY = "eu_regulatory"
    GLOBAL_TECH = "global_tech"
    GENERIC = "generic"


_RE_CYRILLIC = re.compile(r"[а-яА-Я]")


# Marker tuples — substring match on lowered query text. Each tuple
# captures the vocabulary that should fire ONLY on that domain. RU
# domains additionally require Cyrillic chars present in the query
# so a casual English mention of "RBC" doesn't trip RU_REAL_ESTATE.

_RU_RE_MARKERS: tuple[str, ...] = (
    "девелопер", "застройщик", "новостройк", "жк ", "жильё", "жилья",
    "жилое", "жилищн", "бизнес-класс", "бизнес класс",
    "премиум-класс", "апартамент", "недвижимост", "строительств",
    "ипотек", "крт", "элитн", "первичк", "вторичк",
)

_RU_AUTOMOTIVE_MARKERS: tuple[str, ...] = (
    "электромобил", "автомобил", "автопром", "автоваз", "лада",
    "москвич", "evolute", "ev ", "локализаци",
    "byd", "geely", "chery", "zeekr", "haval", "автоконцерн",
    "автостат", "минпромторг",
)

_RU_TECH_SAAS_MARKERS: tuple[str, ...] = (
    "saas", "стартап", "ит-сектор", "it-сектор", "b2b",
    "финтех", "fintech", "программное обеспечение", "разработчик",
    "продуктов",  # "продуктовая разработка" / IT product
)

_EU_REGULATORY_MARKERS: tuple[str, ...] = (
    "eu ", "european", "europe", "europa", "ec.europa",
    "directive", "crcf", "ets ", "ets,",
    "european commission", "european parliament",
)

_GLOBAL_TECH_MARKERS: tuple[str, ...] = (
    "llm", "observability", "saas platforms", "enterprise scale",
    "machine learning", "vector database", "open source",
    "kubernetes", "openai", "anthropic", "langchain",
    "langfuse", "langsmith", "helicone",
)


def detect_query_domain(query: str) -> QueryDomain:
    """Classify *query* into one of the known QueryDomain values.

    Order of checks (most-specific first):
      1. RU_REAL_ESTATE (cyrillic + RE-vocab) — flagship domain
      2. RU_AUTOMOTIVE (cyrillic + auto-vocab)
      3. RU_TECH_SAAS (cyrillic + tech/SaaS vocab)
      4. EU_REGULATORY (any language + EU/regulation markers)
      5. GLOBAL_TECH (LLM / observability / vendor names)
      6. GENERIC fallback

    Synchronous despite trivial cost — keeps the call graph simple.
    Async signature deliberately avoided so callers don't have to
    await a no-op operation; if a future Phase 4 LLM-fallback adds
    latency we'll introduce an async variant alongside.
    """
    if not query or not query.strip():
        return QueryDomain.GENERIC

    q_lower = query.lower()
    has_cyrillic = bool(_RE_CYRILLIC.search(query))

    if has_cyrillic and _any_marker(q_lower, _RU_RE_MARKERS):
        return QueryDomain.RU_REAL_ESTATE
    if has_cyrillic and _any_marker(q_lower, _RU_AUTOMOTIVE_MARKERS):
        return QueryDomain.RU_AUTOMOTIVE
    if has_cyrillic and _any_marker(q_lower, _RU_TECH_SAAS_MARKERS):
        return QueryDomain.RU_TECH_SAAS
    if _any_marker(q_lower, _EU_REGULATORY_MARKERS):
        return QueryDomain.EU_REGULATORY
    if _any_marker(q_lower, _GLOBAL_TECH_MARKERS):
        return QueryDomain.GLOBAL_TECH
    return QueryDomain.GENERIC


def _any_marker(q_lower: str, markers: tuple[str, ...]) -> bool:
    return any(m in q_lower for m in markers)
