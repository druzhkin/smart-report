"""Valyu-first routing matrix (v3 brief §3.2 + §3.5).

Replaces the v1-brief-era `BACKEND_PLAN_BY_DOMAIN` in `domain_detector.py`
as the canonical routing surface. The v1 plan is kept in
`domain_detector.py` for backward compatibility with Day 3 tests until
the SearchOrchestrator migrates over.

Architectural invariant (v3 §0): on every domain Valyu covers (financial,
regulatory, medical, scientific, legal, technical_research), Valyu MUST
be primary — not "preferred", *always*. Augment backends (Tavily, Exa,
Perplexity) only run when Valyu returns empty/error, in which case the
DOCX renderer surfaces a degradation warning the user can act on (§3.4).

The invariant is enforced by `tests/test_routing_invariants.py`. That
test cannot be skipped, deleted, or modified to pass — see brief §3.5.

Note on real coverage: per `docs/VALYU_CAPABILITY_MAP.md`, two of the
"covered" domains have known structural gaps in Valyu's corpus today:
  * regulatory_eu — NO eur-lex / europa.eu native dataset
  * financial_global — only US-focused datasets exist
For those queries we expect to hit the degradation path on every call
until Valyu expands their corpus. That's intentional — the warning
surfaces the gap rather than papering over it.
"""

from __future__ import annotations

from typing import Optional

# Backend identifiers as plain strings (no enum dependency) so the
# invariant test stays trivial to read and impossible to mis-import.
VALYU = "valyu"
EXA = "exa"
TAVILY_BASIC = "tavily_basic"
TAVILY_ADVANCED = "tavily_advanced"
PERPLEXITY = "perplexity"


# (primary, augment) per detected_domain. Augment is None when no
# fallback exists (the russian/general buckets are not Valyu-covered
# in the first place; brief routes them to Perplexity / Tavily basic
# directly, with the other as augment).
ROUTING_MATRIX: dict[str, tuple[str, Optional[str]]] = {
    "financial_us": (VALYU, TAVILY_ADVANCED),
    "financial_global": (VALYU, TAVILY_ADVANCED),
    "regulatory_eu": (VALYU, TAVILY_ADVANCED),
    "regulatory_us": (VALYU, TAVILY_ADVANCED),
    "medical_clinical": (VALYU, EXA),
    "scientific": (VALYU, EXA),
    "legal": (VALYU, EXA),
    "technical_research": (VALYU, TAVILY_ADVANCED),
    "russian_market": (PERPLEXITY, TAVILY_BASIC),
    "realtime_news": (TAVILY_BASIC, PERPLEXITY),
    "general": (TAVILY_BASIC, PERPLEXITY),
}


# The 8 domains where Valyu MUST be primary. The invariant test asserts
# this list against ROUTING_MATRIX; both must agree.
VALYU_COVERED_DOMAINS: tuple[str, ...] = (
    "financial_us",
    "financial_global",
    "regulatory_eu",
    "regulatory_us",
    "medical_clinical",
    "scientific",
    "legal",
    "technical_research",
)


# Domains where Valyu has known structural coverage gaps despite the
# invariant. Useful for telemetry / per-domain expected-degradation
# tracking. NOT a routing decision — the invariant still holds; this
# is a heads-up for downstream metrics.
VALYU_KNOWN_GAP_DOMAINS: tuple[str, ...] = (
    "regulatory_eu",      # no eur-lex / europa native dataset
    "financial_global",   # US-only datasets in proprietary tier
)


def primary_for(domain: str) -> str:
    """Return the primary backend name for *domain*.

    Raises KeyError if the domain isn't in the matrix — callers should
    map their detected_domain to one of the matrix keys before invoking.
    """
    return ROUTING_MATRIX[domain][0]


def augment_for(domain: str) -> Optional[str]:
    """Return the augment backend name (or None) for *domain*."""
    return ROUTING_MATRIX[domain][1]
