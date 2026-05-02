"""Domain-aware research policy and source registry.

The goal is to make source collection intentional: each domain gets required
source tiers, preferred providers, and a warning when the current evidence base
does not contain enough primary/authoritative material.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from .domain_detector import QueryDomain, detect_query_domain
from .models import FinalReport

SourceTier = Literal["tier1_primary", "tier2_industry", "tier3_secondary", "weak"]


@dataclass(frozen=True)
class DomainResearchPolicy:
    domain: QueryDomain
    preferred_services: tuple[str, ...]
    required_source_families: tuple[str, ...]
    tier1_domains: tuple[str, ...] = field(default_factory=tuple)
    tier2_domains: tuple[str, ...] = field(default_factory=tuple)
    min_tier1_sources: int = 2
    min_total_sources: int = 8


class _PolicyBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceCoverageItem(_PolicyBase):
    url: str
    title: str = ""
    tier: SourceTier
    matched_family: str = ""


class ResearchPolicyAssessment(_PolicyBase):
    domain: str
    recommended_services: list[str]
    required_source_families: list[str]
    requires_academic_retrieval: bool = False
    academic_retrieval_satisfied: bool = False
    tier1_count: int
    tier2_count: int
    total_sources: int
    missing_source_families: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    sources: list[SourceCoverageItem] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


POLICIES: dict[QueryDomain, DomainResearchPolicy] = {
    QueryDomain.RU_REAL_ESTATE: DomainResearchPolicy(
        domain=QueryDomain.RU_REAL_ESTATE,
        preferred_services=("perplexity", "valyu", "tavily"),
        required_source_families=("cbr", "domrf", "rosstat", "erz", "mos"),
        tier1_domains=("cbr.ru", "дом.рф", "xn--d1aqf.xn--p1ai", "rosstat.gov.ru", "mos.ru"),
        tier2_domains=("erzrf.ru", "metrium.ru", "cian.ru", "bnmap.pro"),
        min_tier1_sources=2,
        min_total_sources=10,
    ),
    QueryDomain.RU_AUTOMOTIVE: DomainResearchPolicy(
        domain=QueryDomain.RU_AUTOMOTIVE,
        preferred_services=("perplexity", "tavily", "valyu"),
        required_source_families=("minpromtorg", "autostat", "aeb", "company"),
        tier1_domains=("minpromtorg.gov.ru", "customs.gov.ru", "government.ru"),
        tier2_domains=("autostat.ru", "aebrus.ru", "kommersant.ru"),
        min_tier1_sources=2,
        min_total_sources=8,
    ),
    QueryDomain.EU_REGULATORY: DomainResearchPolicy(
        domain=QueryDomain.EU_REGULATORY,
        preferred_services=("valyu", "perplexity", "tavily"),
        required_source_families=("europa", "commission", "parliament", "legal_text"),
        tier1_domains=("europa.eu", "ec.europa.eu", "europarl.europa.eu", "eur-lex.europa.eu"),
        tier2_domains=("oecd.org", "bruegel.org", "ceps.eu"),
        min_tier1_sources=3,
        min_total_sources=8,
    ),
    QueryDomain.GLOBAL_TECH: DomainResearchPolicy(
        domain=QueryDomain.GLOBAL_TECH,
        preferred_services=("paper_search", "exa", "perplexity", "valyu"),
        required_source_families=("academic", "vendor_docs", "benchmark", "github"),
        tier1_domains=("arxiv.org", "acm.org", "ieee.org", "github.com"),
        tier2_domains=("semanticscholar.org", "openai.com", "anthropic.com", "microsoft.com"),
        min_tier1_sources=2,
        min_total_sources=8,
    ),
    QueryDomain.ACADEMIC_RESEARCH: DomainResearchPolicy(
        domain=QueryDomain.ACADEMIC_RESEARCH,
        preferred_services=("paper_search", "valyu", "exa", "perplexity"),
        required_source_families=("academic", "benchmark"),
        tier1_domains=(
            "arxiv.org",
            "pubmed.ncbi.nlm.nih.gov",
            "semanticscholar.org",
            "doi.org",
            "clinicaltrials.gov",
            "acm.org",
            "ieee.org",
        ),
        tier2_domains=("biorxiv.org", "medrxiv.org", "crossref.org", "paperswithcode.com"),
        min_tier1_sources=2,
        min_total_sources=6,
    ),
    QueryDomain.RU_TECH_SAAS: DomainResearchPolicy(
        domain=QueryDomain.RU_TECH_SAAS,
        preferred_services=("perplexity", "tavily", "exa"),
        required_source_families=("company", "market", "regulatory", "benchmark"),
        tier1_domains=("nalog.gov.ru", "cbr.ru", "mincifra.gov.ru"),
        tier2_domains=("tadviser.ru", "cnews.ru", "vc.ru", "rb.ru"),
        min_tier1_sources=1,
        min_total_sources=8,
    ),
    QueryDomain.GENERIC: DomainResearchPolicy(
        domain=QueryDomain.GENERIC,
        preferred_services=("perplexity", "tavily", "exa", "paper_search"),
        required_source_families=("primary", "industry", "benchmark"),
        tier1_domains=(".gov", ".edu", "europa.eu", "arxiv.org"),
        tier2_domains=("reuters.com", "bloomberg.com", "ft.com", "mckinsey.com", "bcg.com"),
        min_tier1_sources=2,
        min_total_sources=8,
    ),
}


def assess_research_policy(
    question: str,
    report: FinalReport | None = None,
) -> ResearchPolicyAssessment:
    domain = detect_query_domain(question)
    policy = POLICIES.get(domain, POLICIES[QueryDomain.GENERIC])
    sources = list(report.all_sources or []) if report else []
    items = [
        _coverage_item(source.url, source.title, policy)
        for source in sources
    ]
    tier1 = sum(1 for item in items if item.tier == "tier1_primary")
    tier2 = sum(1 for item in items if item.tier == "tier2_industry")
    families = {item.matched_family for item in items if item.matched_family}
    requires_academic = policy.preferred_services[0] == "paper_search" or "academic" in policy.required_source_families
    academic_satisfied = any(
        "paper_search" in (source.tool or "").lower()
        or item.matched_family == "academic"
        or any(marker in item.url.lower() for marker in ("arxiv.org", "pubmed", "doi.org", "semanticscholar"))
        for source, item in zip(sources, items, strict=False)
    )
    missing = [family for family in policy.required_source_families if family not in families]
    issues: list[str] = []
    if len(sources) < policy.min_total_sources:
        issues.append(f"Needs at least {policy.min_total_sources} total sources for {domain.value}.")
    if tier1 < policy.min_tier1_sources:
        issues.append(f"Needs at least {policy.min_tier1_sources} tier-1/primary sources.")
    if missing:
        issues.append("Missing source families: " + ", ".join(missing) + ".")
    if requires_academic and not academic_satisfied:
        issues.append("Academic retrieval is required; run paper_search or provide academic sources.")
    return ResearchPolicyAssessment(
        domain=domain.value,
        recommended_services=list(policy.preferred_services),
        required_source_families=list(policy.required_source_families),
        requires_academic_retrieval=requires_academic,
        academic_retrieval_satisfied=academic_satisfied,
        tier1_count=tier1,
        tier2_count=tier2,
        total_sources=len(sources),
        missing_source_families=missing,
        issues=issues,
        sources=items,
    )


def recommended_service_for_policy(question: str, candidate_sources: list[str]) -> str:
    policy = POLICIES.get(detect_query_domain(question), POLICIES[QueryDomain.GENERIC])
    joined = " ".join(candidate_sources).lower()
    if policy.preferred_services[0] == "paper_search":
        return "paper_search"
    if any("arxiv" in item or "pubmed" in item or "academic" in item for item in candidate_sources):
        return "paper_search"
    if any(domain in joined for domain in policy.tier1_domains):
        return policy.preferred_services[0]
    return policy.preferred_services[0]


def _coverage_item(url: str, title: str, policy: DomainResearchPolicy) -> SourceCoverageItem:
    text = f"{_host(url)} {url} {title}".lower()
    family = _family_for(text)
    if any(marker in text for marker in policy.tier1_domains):
        tier: SourceTier = "tier1_primary"
    elif any(marker in text for marker in policy.tier2_domains):
        tier = "tier2_industry"
    elif any(marker in text for marker in ("blog", "medium.com", "vc.ru")):
        tier = "weak"
    else:
        tier = "tier3_secondary"
    return SourceCoverageItem(url=url, title=title or "", tier=tier, matched_family=family)


def _family_for(text: str) -> str:
    families = {
        "cbr": ("cbr.ru", "central bank", "банк россии"),
        "domrf": ("дом.рф", "dom.rf", "xn--d1aqf"),
        "rosstat": ("rosstat", "росстат"),
        "erz": ("erzrf", "ерз"),
        "mos": ("mos.ru", "стройкомплекс"),
        "academic": ("arxiv", "pubmed", "semantic", "doi", "journal"),
        "vendor_docs": ("docs.", "documentation", "github.com"),
        "benchmark": ("benchmark", "mckinsey", "bcg", "gartner", "forrester"),
        "github": ("github.com",),
        "europa": ("europa.eu",),
        "commission": ("ec.europa.eu", "commission"),
        "parliament": ("europarl", "parliament"),
        "legal_text": ("eur-lex", "directive", "regulation"),
        "minpromtorg": ("minpromtorg",),
        "autostat": ("autostat",),
        "aeb": ("aebrus",),
        "company": ("company", "annual report", "developer", "issuer"),
        "market": ("market", "industry", "аналит"),
        "regulatory": ("regulator", "gov.ru", ".gov"),
        "primary": (".gov", ".edu", "official"),
        "industry": ("industry", "association", "agency"),
    }
    for family, markers in families.items():
        if any(marker in text for marker in markers):
            return family
    return ""


def _host(url: str) -> str:
    return urlparse(url or "").netloc.lower()
