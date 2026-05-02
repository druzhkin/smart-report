"""Research brief quality contract before synthesis.

This layer evaluates the analytical input package: uploaded source reports,
normalized intake facts, analyzer output, research policy, and the visual data
available for the final report. It is deliberately deterministic and can be
shown in the UI before the user spends more money on synthesis/export.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, date, datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from .domain_detector import detect_query_domain
from .models import AnalysisOutput, NormalizedReport, ResearchPrompt, UploadedMarkdown
from .research_policy import assess_research_policy


class _BriefBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


BriefSeverity = Literal["critical", "major", "minor"]
VisualPlanKind = Literal[
    "source_matrix",
    "numeric_fact_table",
    "conflict_register",
    "evidence_gap_register",
    "trend_or_ranking_chart",
    "source_quality_chart",
]


class ResearchBriefIssue(_BriefBase):
    code: str
    severity: BriefSeverity
    message: str
    recommendation: str = ""


class SourceMix(_BriefBase):
    total_sources: int
    primary_like_sources: int
    academic_sources: int
    official_sources: int
    industry_sources: int
    weak_sources: int
    domains: dict[str, int] = Field(default_factory=dict)


class FactFreshnessSummary(_BriefBase):
    total_numeric_facts: int
    high_relevance_numeric_facts: int
    dated_or_unknown_facts: int
    recent_or_current_facts: int


class CounterEvidenceSummary(_BriefBase):
    conflict_count: int
    critical_conflict_count: int
    gap_count: int
    unverified_number_count: int
    counter_evidence_present: bool


class VisualDataPlanItem(_BriefBase):
    kind: VisualPlanKind
    title: str
    reason: str
    ready: bool
    required_inputs: list[str] = Field(default_factory=list)


class EvidenceToClaimMapItem(_BriefBase):
    target: str
    available_evidence_count: int
    source_refs: list[str] = Field(default_factory=list)
    ready: bool


class ResearchBriefQuality(_BriefBase):
    score: int
    passed: bool
    verdict: Literal["ready_for_synthesis", "needs_followup", "blocked"]
    domain: str
    recommended_services: list[str] = Field(default_factory=list)
    source_mix: SourceMix
    freshness: FactFreshnessSummary
    counter_evidence: CounterEvidenceSummary
    evidence_to_claim_map: list[EvidenceToClaimMapItem] = Field(default_factory=list)
    visual_plan: list[VisualDataPlanItem] = Field(default_factory=list)
    issues: list[ResearchBriefIssue] = Field(default_factory=list)


def evaluate_research_brief(
    question: str,
    *,
    research_prompt: ResearchPrompt | None = None,
    source_reports: list[UploadedMarkdown] | None = None,
    normalized_reports: list[NormalizedReport] | None = None,
    analysis: AnalysisOutput | None = None,
) -> ResearchBriefQuality:
    del research_prompt
    source_reports = list(source_reports or [])
    normalized_reports = list(normalized_reports or [])
    sources = _collect_source_refs(normalized_reports, source_reports)
    source_mix = _source_mix(sources)
    freshness = _freshness_summary(normalized_reports, analysis)
    counter = _counter_summary(analysis)
    evidence_map = _evidence_to_claim_map(analysis, sources)
    visual_plan = _visual_plan(source_mix, freshness, counter, analysis)
    policy_report = _policy_projection(question, sources)
    policy = assess_research_policy(question, policy_report)

    issues: list[ResearchBriefIssue] = []
    if len(source_reports) < 2:
        issues.append(
            ResearchBriefIssue(
                code="research_brief_too_few_reports",
                severity="major",
                message=f"Only {len(source_reports)} source report(s) are uploaded.",
                recommendation="Run at least two independent research passes or upload independent source packs.",
            )
        )
    if not policy.passed:
        issues.append(
            ResearchBriefIssue(
                code="research_brief_policy_failed",
                severity="critical" if policy.requires_academic_retrieval else "major",
                message="; ".join(policy.issues),
                recommendation="Use the recommended services/source families before synthesis.",
            )
        )
    if freshness.high_relevance_numeric_facts < 8:
        issues.append(
            ResearchBriefIssue(
                code="research_brief_facts_too_thin",
                severity="major",
                message=(
                    f"Only {freshness.high_relevance_numeric_facts} high/medium relevance "
                    "numeric fact(s) are available."
                ),
                recommendation="Run targeted follow-up for quantified evidence before final synthesis.",
            )
        )
    if freshness.total_numeric_facts and freshness.dated_or_unknown_facts > freshness.recent_or_current_facts:
        issues.append(
            ResearchBriefIssue(
                code="research_brief_freshness_weak",
                severity="major",
                message="Most numeric facts are dated or have unknown freshness.",
                recommendation="Refresh the critical numbers or mark the report as limited.",
            )
        )
    if analysis is not None and not counter.counter_evidence_present:
        issues.append(
            ResearchBriefIssue(
                code="research_brief_no_counter_evidence",
                severity="major",
                message="Analyzer has not surfaced conflicts, gaps, or unverified numbers.",
                recommendation="Run a disconfirming-evidence pass instead of only collecting supporting facts.",
            )
        )
    if sum(1 for item in visual_plan if item.ready) < 3:
        issues.append(
            ResearchBriefIssue(
                code="research_brief_visual_data_not_ready",
                severity="major",
                message="Fewer than three visual data blocks are ready.",
                recommendation="Collect enough source/fact/conflict data to build exhibits before synthesis.",
            )
        )
    if any(not item.ready for item in evidence_map):
        issues.append(
            ResearchBriefIssue(
                code="research_brief_claim_map_incomplete",
                severity="major",
                message="Some planned claim groups lack evidence support.",
                recommendation="Close the unsupported claim groups with targeted follow-up.",
            )
        )

    critical = sum(1 for issue in issues if issue.severity == "critical")
    major = sum(1 for issue in issues if issue.severity == "major")
    minor = sum(1 for issue in issues if issue.severity == "minor")
    score = max(
        0,
        min(
            100,
            100
            - critical * 30
            - major * 12
            - minor * 4
            + min(10, freshness.high_relevance_numeric_facts // 4)
            + min(8, source_mix.primary_like_sources * 2),
        ),
    )
    passed = critical == 0 and major == 0 and score >= 80
    verdict: Literal["ready_for_synthesis", "needs_followup", "blocked"]
    if critical:
        verdict = "blocked"
    elif passed:
        verdict = "ready_for_synthesis"
    else:
        verdict = "needs_followup"
    return ResearchBriefQuality(
        score=score,
        passed=passed,
        verdict=verdict,
        domain=detect_query_domain(question).value,
        recommended_services=policy.recommended_services,
        source_mix=source_mix,
        freshness=freshness,
        counter_evidence=counter,
        evidence_to_claim_map=evidence_map,
        visual_plan=visual_plan,
        issues=issues,
    )


def _collect_source_refs(
    normalized_reports: list[NormalizedReport],
    source_reports: list[UploadedMarkdown],
) -> list[tuple[str, str]]:
    refs: dict[str, str] = {}
    for report in normalized_reports:
        for source in report.extracted_sources_inventory:
            if source.url:
                refs[source.url] = source.title or source.url
        for fact in report.extracted_numeric_facts:
            for source in fact.sources:
                if source.url:
                    refs[source.url] = source.title or source.url
        for fact in report.extracted_qualitative_facts:
            for source in fact.sources:
                if source.url:
                    refs[source.url] = source.title or source.url
    for upload in source_reports:
        for url in re.findall(r"https?://[^\s)\]]+", upload.content or ""):
            clean = url.rstrip(".,;)")
            refs.setdefault(clean, clean)
    return list(refs.items())


def _source_mix(sources: list[tuple[str, str]]) -> SourceMix:
    domains = Counter(_host(url) for url, _ in sources if _host(url))
    academic = 0
    official = 0
    industry = 0
    weak = 0
    primary = 0
    for url, title in sources:
        text = f"{url} {title}".lower()
        if any(marker in text for marker in ("arxiv", "pubmed", "doi.org", "semantic", "ieee", "acm")):
            academic += 1
            primary += 1
        elif any(marker in text for marker in (".gov", "gov.", "europa.eu", "cbr.ru", "rosstat", "sec.gov")):
            official += 1
            primary += 1
        elif any(marker in text for marker in ("mckinsey", "bcg", "gartner", "forrester", "cbre", "jll")):
            industry += 1
        elif any(marker in text for marker in ("blog", "medium.com", "vc.ru", "reddit")):
            weak += 1
        else:
            industry += 1
    return SourceMix(
        total_sources=len(sources),
        primary_like_sources=primary,
        academic_sources=academic,
        official_sources=official,
        industry_sources=industry,
        weak_sources=weak,
        domains=dict(domains.most_common(12)),
    )


def _freshness_summary(
    normalized_reports: list[NormalizedReport],
    analysis: AnalysisOutput | None,
) -> FactFreshnessSummary:
    facts = []
    for report in normalized_reports:
        facts.extend(report.extracted_numeric_facts)
    if analysis is not None and not facts:
        facts.extend(analysis.all_numeric_facts)
    high = [fact for fact in facts if fact.relevance_to_question in {"high", "medium"}]
    recent = 0
    dated = 0
    for fact in facts:
        year = _extract_year(" ".join([fact.timeframe or "", fact.source_quote or ""]))
        if year is not None and year >= date.today().year - 2:
            recent += 1
        else:
            dated += 1
    return FactFreshnessSummary(
        total_numeric_facts=len(facts),
        high_relevance_numeric_facts=len(high),
        dated_or_unknown_facts=dated,
        recent_or_current_facts=recent,
    )


def _counter_summary(analysis: AnalysisOutput | None) -> CounterEvidenceSummary:
    if analysis is None:
        return CounterEvidenceSummary(
            conflict_count=0,
            critical_conflict_count=0,
            gap_count=0,
            unverified_number_count=0,
            counter_evidence_present=False,
        )
    critical = sum(1 for conflict in analysis.conflicts if conflict.importance == "critical")
    return CounterEvidenceSummary(
        conflict_count=len(analysis.conflicts),
        critical_conflict_count=critical,
        gap_count=len(analysis.gaps),
        unverified_number_count=len(analysis.unverified_numbers),
        counter_evidence_present=bool(
            analysis.conflicts or analysis.gaps or analysis.unverified_numbers
        ),
    )


def _evidence_to_claim_map(
    analysis: AnalysisOutput | None,
    sources: list[tuple[str, str]],
) -> list[EvidenceToClaimMapItem]:
    urls = [url for url, _ in sources[:8]]
    if analysis is None:
        return []
    items: list[EvidenceToClaimMapItem] = []
    for claim in analysis.consensus[:6]:
        support = list(claim.supporting_sources or [])
        items.append(
            EvidenceToClaimMapItem(
                target=claim.claim,
                available_evidence_count=len(support),
                source_refs=support[:6] or urls[:3],
                ready=len(support) >= 1 or bool(urls),
            )
        )
    for conflict in analysis.conflicts[:4]:
        refs = [item for item in [conflict.source_a, conflict.source_b] if item]
        items.append(
            EvidenceToClaimMapItem(
                target=f"Resolve conflict: {conflict.topic}",
                available_evidence_count=len(refs),
                source_refs=refs,
                ready=bool(conflict.resolution_hint and len(refs) >= 2),
            )
        )
    return items


def _visual_plan(
    source_mix: SourceMix,
    freshness: FactFreshnessSummary,
    counter: CounterEvidenceSummary,
    analysis: AnalysisOutput | None,
) -> list[VisualDataPlanItem]:
    facts_ready = freshness.high_relevance_numeric_facts >= 5
    plan = [
        VisualDataPlanItem(
            kind="source_matrix",
            title="Source reliability matrix",
            reason="Shows whether the evidence base is credible enough.",
            ready=source_mix.total_sources >= 4,
            required_inputs=["source inventory"],
        ),
        VisualDataPlanItem(
            kind="source_quality_chart",
            title="Source quality mix",
            reason="Makes weak versus primary source dependence visible.",
            ready=source_mix.total_sources >= 4,
            required_inputs=["source reliability labels"],
        ),
        VisualDataPlanItem(
            kind="numeric_fact_table",
            title="Key numeric facts",
            reason="Turns raw facts into a report exhibit.",
            ready=facts_ready,
            required_inputs=["numeric facts"],
        ),
        VisualDataPlanItem(
            kind="trend_or_ranking_chart",
            title="Trend or ranking chart",
            reason="Supports the main quantified thesis visually.",
            ready=facts_ready,
            required_inputs=["comparable numeric facts"],
        ),
        VisualDataPlanItem(
            kind="conflict_register",
            title="Conflict register",
            reason="Shows what evidence does not agree on.",
            ready=counter.conflict_count > 0,
            required_inputs=["analyzer conflicts"],
        ),
        VisualDataPlanItem(
            kind="evidence_gap_register",
            title="Evidence gap register",
            reason="Prevents hidden limitations.",
            ready=counter.gap_count > 0 or (analysis is not None and bool(analysis.followup_prompt)),
            required_inputs=["analyzer gaps/follow-up prompts"],
        ),
    ]
    return plan


def _policy_projection(question: str, sources: list[tuple[str, str]]):
    from .models import ExecutiveSummaryV4, FinalReport, Source

    return FinalReport(
        session_id="research-brief",
        question=question,
        executive_summary=ExecutiveSummaryV4(main_answer="Research brief projection."),
        all_sources=[
            Source(title=title or url, url=url, tool=_tool_for_url(url))
            for url, title in sources
        ],
    )


def _tool_for_url(url: str) -> str:
    lowered = url.lower()
    if any(marker in lowered for marker in ("arxiv", "pubmed", "doi.org", "semantic")):
        return "paper_search_mcp"
    return "uploaded_source"


def _host(url: str) -> str:
    return urlparse(url or "").netloc.lower()


def _extract_year(text: str) -> int | None:
    years = [int(match) for match in re.findall(r"\b(20\d{2})\b", text or "")]
    if not years:
        return None
    current = datetime.now(UTC).year
    plausible = [year for year in years if 2000 <= year <= current + 1]
    return max(plausible) if plausible else None
