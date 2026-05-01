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
from dataclasses import dataclass
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


# ---------------------------------------------------------------------------
# Backend routing (v4.5 week-7 Day 3)
# ---------------------------------------------------------------------------
#
# Maps each detected domain to a primary→fallback backend plan. Two backends
# exist today:
#   * VALYU — auto-retrieve via Valyu DeepSearch SDK (smart_report.sources.valyu)
#   * PERPLEXITY_MANUAL — defer to the v4 manual DR loop. We do NOT
#     auto-call Perplexity from this codebase yet; the orchestrator
#     surfaces a sentinel so the caller knows to drive Perplexity by
#     hand. Brief §3.6 frames this as "Perplexity primary" in the
#     routing table; that's faithful provided the manual loop fills
#     the role.
#
# Routing decisions follow brief §3.6 mapped onto the existing 6 QueryDomain
# values (the brief's own labels — financial_us / regulatory_eu / etc. —
# don't match our enum exactly):
#   RU_REAL_ESTATE / RU_AUTOMOTIVE / RU_TECH_SAAS → Russian sources are
#     not in Valyu's corpus (confirmed by Day 1 capability map). Manual
#     Perplexity is the only viable primary; no Valyu fallback.
#   EU_REGULATORY → Valyu primary (proprietary EU regulatory corpus is
#     real value-add). search_type="proprietary", fast_mode=False
#     (closes BLOCKERS.md A3). Manual Perplexity fallback if Valyu
#     returns nothing.
#   GLOBAL_TECH → Manual Perplexity primary (better recall on vendor
#     blogs / changelogs / GitHub). Valyu fallback as acceleration via
#     arxiv corpus (search_type="all", fast_mode=True is fine).
#   GENERIC → Manual Perplexity primary (broad recall). Valyu fallback
#     as cheap acceleration.


class Backend(str, Enum):
    """Search backends available to the SearchOrchestrator."""

    VALYU = "valyu"
    PERPLEXITY_MANUAL = "perplexity_manual"


@dataclass(frozen=True)
class ValyuCallSpec:
    """How to invoke ValyuClient.search() for a given routing decision.

    The brief's A3 finding (BLOCKERS.md) means the right (search_type,
    fast_mode) combo depends on whether we're after Valyu's value-add
    proprietary corpora or just using it as a cheap acceleration. Bake
    the choice into the routing rule so callers can't accidentally
    burn budget or ask for an API-incompatible combo.
    """

    search_type: str = "all"
    fast_mode: bool = True
    category: str | None = None
    included_sources: list[str] | None = None
    relevance_threshold: float = 0.5


@dataclass(frozen=True)
class BackendPlan:
    """Primary + optional fallback backend selection for a domain."""

    primary: Backend
    fallback: Backend | None
    valyu_spec: ValyuCallSpec | None = None


_PROPRIETARY_VALYU = ValyuCallSpec(
    search_type="proprietary", fast_mode=False, relevance_threshold=0.5
)
_FAST_WEB_VALYU = ValyuCallSpec(
    search_type="all", fast_mode=True, relevance_threshold=0.5
)
_ARXIV_VALYU = ValyuCallSpec(
    search_type="proprietary",
    fast_mode=False,
    included_sources=["valyu/valyu-arxiv"],
    relevance_threshold=0.5,
)


BACKEND_PLAN_BY_DOMAIN: dict[QueryDomain, BackendPlan] = {
    QueryDomain.RU_REAL_ESTATE: BackendPlan(
        primary=Backend.PERPLEXITY_MANUAL, fallback=None, valyu_spec=None
    ),
    QueryDomain.RU_AUTOMOTIVE: BackendPlan(
        primary=Backend.PERPLEXITY_MANUAL, fallback=None, valyu_spec=None
    ),
    QueryDomain.RU_TECH_SAAS: BackendPlan(
        primary=Backend.PERPLEXITY_MANUAL, fallback=None, valyu_spec=None
    ),
    QueryDomain.EU_REGULATORY: BackendPlan(
        primary=Backend.VALYU,
        fallback=Backend.PERPLEXITY_MANUAL,
        valyu_spec=_PROPRIETARY_VALYU,
    ),
    QueryDomain.GLOBAL_TECH: BackendPlan(
        primary=Backend.PERPLEXITY_MANUAL,
        fallback=Backend.VALYU,
        valyu_spec=_ARXIV_VALYU,
    ),
    QueryDomain.GENERIC: BackendPlan(
        primary=Backend.PERPLEXITY_MANUAL,
        fallback=Backend.VALYU,
        valyu_spec=_FAST_WEB_VALYU,
    ),
}


def backend_plan_for(query: str) -> BackendPlan:
    """Convenience: detect domain and return the routing plan in one call."""
    return BACKEND_PLAN_BY_DOMAIN[detect_query_domain(query)]
