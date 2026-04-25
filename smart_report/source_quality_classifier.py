"""Heuristic source-quality classifier (v4.5 Phase 3 Step 3.3).

Comparison Run 1 finding 2: evidence-grade tagging in the synthesizer
inherits whatever the input markdown already contains. If a DR tool
cited "по данным РБК" we passed through a WEAK tag; if it cited "EU
Regulation 2024/3012" we passed through a STRONG tag. The grade was
the source's, not ours.

This module gives the analyzer (and through it the synthesizer) a
deterministic per-domain self-assessed grade based on the source URL:

  primary_regulator     → STRONG  (registry hit for the query domain)
  first_party_data      → STRONG  (subset — government registries)
  established_consultancy → MODERATE (Big-N + Russian RE consultancies)
  trusted_media         → MODERATE  (RU/global business press)
  vendor_blog           → WEAK    (default for unknown)
  forum_or_aggregator   → WEAK    (Reddit / Quora / Medium / Habr)
  unknown               → WEAK    (no signal at all)

The output is a SourceQualityScore that the synthesizer can use to
override input-side tags. No LLM call — $0/source/lookup.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .authoritative_sources import is_authoritative_url_for_domain
from .domain_detector import QueryDomain


DomainAuthority = Literal[
    "primary_regulator",
    "first_party_data",
    "established_consultancy",
    "trusted_media",
    "vendor_blog",
    "forum_or_aggregator",
    "unknown",
]


EvidenceStrength = Literal["STRONG", "MODERATE", "WEAK", "SPECULATIVE"]


class SourceQualityScore(BaseModel):
    url: str
    domain_authority: DomainAuthority
    evidence_strength: EvidenceStrength
    rationale: str


# ---------------------------------------------------------------------------
# Tiered domain sets — heuristic, lowercase, substring-matched against URL
# ---------------------------------------------------------------------------


# RU + global business press (≈MODERATE strength). Does NOT include
# vendor blogs masquerading as press; those fall to the VENDOR_BLOG tier
# by default.
_TRUSTED_MEDIA_DOMAINS: frozenset[str] = frozenset({
    # Russian business press
    "rbc.ru",
    "kommersant.ru",
    "vedomosti.ru",
    "interfax.ru",
    "ria.ru",
    "tass.ru",
    "themoscowtimes.com",
    "rg.ru",            # Российская газета
    "expert.ru",
    "forbes.ru",
    # Global business press
    "ft.com",
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "nytimes.com",
    "economist.com",
    "axios.com",
    "politico.eu",
})


# Consultancies / professional services with first-party research arms.
# Lower than primary_regulator but higher than trusted_media because
# their reports are typically based on proprietary data.
_ESTABLISHED_CONSULTANCY_DOMAINS: frozenset[str] = frozenset({
    # International Big-N + RE-specific
    "jll.com", "jllrussia.com",
    "cbre.com", "cbre.ru",
    "knightfrank.com", "knightfrank.ru",
    "colliers.com",
    "cushmanwakefield.com",
    "savills.com",
    # Big management consultancies
    "mckinsey.com",
    "bcg.com",
    "bain.com",
    "deloitte.com",
    "pwc.com",
    "ey.com",
    "kpmg.com",
    "rolandberger.com",
    "oliverwyman.com",
    "accenture.com",
    # RU consultancy / strategy
    "yakovpartners.com",
    "strategy.ru",
    "rbc.consulting",
    "nfgroup.ru",
    "metrium.ru",
    "nikoliers.com",
})


# Forum / aggregator / user-generated content patterns — low signal,
# possible value but no editorial accountability.
_FORUM_OR_AGGREGATOR_PATTERNS: tuple[str, ...] = (
    "reddit.com",
    "quora.com",
    "medium.com",
    "habr.com",
    "stackoverflow.com",
    "stackexchange.com",
    "linkedin.com/posts",
    "linkedin.com/pulse",
    "twitter.com/",
    "x.com/",
    "facebook.com/",
    "youtube.com/",
    "telegram.me/",
    "t.me/",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_source(url: str, query_domain: QueryDomain) -> SourceQualityScore:
    """Classify *url* into a domain-authority + evidence-strength tier.

    The order of checks is intentional:
      1. Empty / opaque → SPECULATIVE (no signal)
      2. Domain-specific authoritative → STRONG (most-trusted tier)
      3. Trusted media → MODERATE
      4. Established consultancy → MODERATE
      5. Forum / aggregator pattern → WEAK
      6. Default → WEAK / unknown

    Cross-domain check is enforced via is_authoritative_url_for_domain:
    autostat.ru is authoritative for RU_AUTOMOTIVE but NOT for
    RU_REAL_ESTATE — the classifier respects that, never silently
    promoting a cross-domain match to STRONG.
    """
    if not url or not url.strip():
        return SourceQualityScore(
            url=url or "",
            domain_authority="unknown",
            evidence_strength="SPECULATIVE",
            rationale="Empty URL — no signal",
        )
    url_lower = url.lower()
    if url_lower.startswith("opaque:"):
        return SourceQualityScore(
            url=url,
            domain_authority="unknown",
            evidence_strength="SPECULATIVE",
            rationale="Opaque tool sentinel, not a real source",
        )

    # Tier 1 — domain-specific authoritative (the strongest signal we have)
    if is_authoritative_url_for_domain(url, query_domain):
        # First-party data subset — government registries get a more
        # specific label, but the same STRONG strength.
        gov_substrings = (".gov.ru", ".gov.eu", "europa.eu", "europarl",
                          "rosstat", "minstroy", "minfin", "minprom", "cbr.ru",
                          "minpromtorg")
        if any(s in url_lower for s in gov_substrings):
            authority = "first_party_data"
        else:
            authority = "primary_regulator"
        return SourceQualityScore(
            url=url,
            domain_authority=authority,
            evidence_strength="STRONG",
            rationale=f"Authoritative {query_domain.value} domain ({authority})",
        )

    # Tier 2 — trusted media
    for d in _TRUSTED_MEDIA_DOMAINS:
        if d in url_lower:
            return SourceQualityScore(
                url=url,
                domain_authority="trusted_media",
                evidence_strength="MODERATE",
                rationale=f"Trusted media outlet ({d})",
            )

    # Tier 3 — established consultancy
    for d in _ESTABLISHED_CONSULTANCY_DOMAINS:
        if d in url_lower:
            return SourceQualityScore(
                url=url,
                domain_authority="established_consultancy",
                evidence_strength="MODERATE",
                rationale=f"Established consultancy ({d})",
            )

    # Tier 4 — forum / aggregator pattern
    for p in _FORUM_OR_AGGREGATOR_PATTERNS:
        if p in url_lower:
            return SourceQualityScore(
                url=url,
                domain_authority="forum_or_aggregator",
                evidence_strength="WEAK",
                rationale=f"Forum / aggregator / UGC pattern ({p})",
            )

    # Default — unknown / vendor blog
    return SourceQualityScore(
        url=url,
        domain_authority="unknown",
        evidence_strength="WEAK",
        rationale="No registry / media / consultancy match — treated as unknown",
    )


def classify_source_batch(
    urls: list[str], query_domain: QueryDomain
) -> dict[str, SourceQualityScore]:
    """Classify a list of URLs in one go; deduplicates by URL."""
    out: dict[str, SourceQualityScore] = {}
    for u in urls:
        if u and u not in out:
            out[u] = classify_source(u, query_domain)
    return out
