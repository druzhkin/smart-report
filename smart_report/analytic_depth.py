"""Deep analytical planning layer.

This module turns a v4 analysis into a non-linear investigation plan: issue
tree, competing hypotheses, research leads, evidence probes, benchmarks, and
monitoring indicators. It is intentionally backend-neutral. A later runner can
execute selected leads with Valyu, Perplexity, OpenAI DR, Exa, or manual upload.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence_audit import assess_evidence_support
from .models import AnalysisOutput, FinalReport, NumericFact, UnverifiedNumber
from .source_authority import count_authoritative_sources


class _DepthBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


AnalyticMethod = Literal[
    "issue_tree",
    "competing_hypotheses",
    "key_assumptions_check",
    "disconfirming_evidence",
    "benchmarking",
    "indicator_signpost",
    "number_verification",
    "source_triangulation",
]

ResearchLeadKind = Literal[
    "close_gap",
    "resolve_conflict",
    "verify_number",
    "explore_anomaly",
    "find_benchmark",
    "strengthen_source_base",
    "support_claim",
    "test_hypothesis",
    "monitor_indicator",
]

ResearchService = Literal[
    "valyu",
    "perplexity",
    "openai",
    "claude",
    "exa",
    "tavily",
    "manual",
]

ResearchPriority = Literal["must", "should", "could"]


class InquiryNode(_DepthBase):
    id: str
    question: str
    rationale: str
    methods: list[AnalyticMethod] = Field(default_factory=list)
    parent_id: str | None = None
    expected_output: str = ""
    children: list[InquiryNode] = Field(default_factory=list)


class CompetingHypothesis(_DepthBase):
    id: str
    statement: str
    why_plausible: str
    would_be_supported_by: list[str] = Field(default_factory=list)
    would_be_weakened_by: list[str] = Field(default_factory=list)
    current_confidence: Literal["high", "medium", "low", "unknown"] = "unknown"


class EvidenceProbe(_DepthBase):
    id: str
    method: AnalyticMethod
    target: str
    question: str
    expected_evidence: str
    disconfirming: bool = False


class ResearchLead(_DepthBase):
    id: str
    kind: ResearchLeadKind
    priority: ResearchPriority
    prompt: str
    rationale: str
    target_entities: list[str] = Field(default_factory=list)
    target_metrics: list[str] = Field(default_factory=list)
    candidate_sources: list[str] = Field(default_factory=list)
    recommended_service: ResearchService = "manual"
    recommended_mode: str | None = None
    linked_to: list[str] = Field(default_factory=list)


class AnalyticDepthPlan(_DepthBase):
    question: str
    domain_hint: str
    root: InquiryNode
    hypotheses: list[CompetingHypothesis]
    evidence_probes: list[EvidenceProbe]
    research_leads: list[ResearchLead]
    benchmark_questions: list[str]
    monitoring_indicators: list[str]
    method_notes: list[str] = Field(default_factory=list)


def build_analytic_depth_plan(
    question: str,
    *,
    analysis: AnalysisOutput | None = None,
    report: FinalReport | None = None,
    max_research_leads: int = 12,
) -> AnalyticDepthPlan:
    """Build a universal non-linear investigation plan from available analysis."""

    clean_question = _clean(question or (report.question if report else ""))
    domain_hint = infer_domain_hint(clean_question, report=report, analysis=analysis)
    hypotheses = _hypotheses(analysis, report)
    probes = _evidence_probes(analysis)
    leads = _research_leads(
        clean_question,
        domain_hint=domain_hint,
        analysis=analysis,
        report=report,
        limit=max_research_leads,
    )
    root = _issue_tree(clean_question, domain_hint=domain_hint, leads=leads)
    return AnalyticDepthPlan(
        question=clean_question,
        domain_hint=domain_hint,
        root=root,
        hypotheses=hypotheses,
        evidence_probes=probes,
        research_leads=leads,
        benchmark_questions=_benchmark_questions(clean_question, domain_hint),
        monitoring_indicators=_monitoring_indicators(analysis, report),
        method_notes=[
            "Use issue trees to decompose the decision space before collecting more data.",
            "Use competing hypotheses to avoid accepting the first persuasive narrative.",
            "Prioritize disconfirming evidence: ask what would make the current answer wrong.",
            "Use Valyu first only where its proprietary datasets are structurally strong.",
        ],
    )


def infer_domain_hint(
    question: str,
    *,
    report: FinalReport | None = None,
    analysis: AnalysisOutput | None = None,
) -> str:
    text = _combined_text(question, report, analysis)
    if _has(text, "sec", "10-k", "10-q", "fred", "earnings", "ticker", "stock", "nasdaq"):
        return "financial_us"
    if _has(text, "clinical", "pubmed", "fda", "trial", "drug", "patient", "medical"):
        return "medical_clinical"
    if _has(text, "arxiv", "paper", "peer-reviewed", "model", "benchmark", "scientific"):
        return "scientific"
    if _has(text, "regulation", "compliance", "law", "sanction", "policy", "legal"):
        return "legal_regulatory"
    if _has(
        text,
        "москва",
        "moscow",
        "russia",
        "россия",
        "российск",
        "цб",
        "дом.рф",
        "ерз",
        "недвиж",
        "real estate",
    ):
        return "russian_market"
    if _has(text, "competitor", "конкур", "market", "рынок", "price", "цена"):
        return "market_general"
    return "general"


def _issue_tree(
    question: str,
    *,
    domain_hint: str,
    leads: list[ResearchLead],
) -> InquiryNode:
    buckets = [
        InquiryNode(
            id="evidence_base",
            question="What facts are already strong, weak, or missing?",
            rationale="A paid report needs a fact map before narrative synthesis.",
            methods=["source_triangulation", "number_verification"],
            parent_id="root",
            expected_output="Evidence table and source quality register.",
        ),
        InquiryNode(
            id="hypotheses",
            question="Which competing explanations can answer the client question?",
            rationale="Alternative explanations reduce confirmation bias.",
            methods=["competing_hypotheses", "disconfirming_evidence"],
            parent_id="root",
            expected_output="Hypothesis matrix with support and contradictions.",
        ),
        InquiryNode(
            id="benchmarks",
            question="What external benchmark makes the answer interpretable?",
            rationale="Numbers without comparators rarely produce a decision.",
            methods=["benchmarking"],
            parent_id="root",
            expected_output="Comparable cases, peer set, historical baseline, or global benchmark.",
        ),
        InquiryNode(
            id="decision",
            question="What decision changes if the evidence changes?",
            rationale="The report must produce action thresholds, not just description.",
            methods=["key_assumptions_check", "indicator_signpost"],
            parent_id="root",
            expected_output="Decision matrix and monitoring signposts.",
        ),
    ]
    for lead in leads[:8]:
        parent_id = _parent_for_lead(lead)
        node = InquiryNode(
            id=f"lead_{lead.id}",
            question=lead.prompt[:220],
            rationale=lead.rationale,
            methods=_methods_for_lead(lead),
            parent_id=parent_id,
            expected_output=_expected_output_for_lead(lead),
        )
        for bucket in buckets:
            if bucket.id == parent_id:
                bucket.children.append(node)
                break
    return InquiryNode(
        id="root",
        question=question or "Build a premium analytical answer.",
        rationale=f"Domain hint: {domain_hint}. The investigation must branch from weak evidence.",
        methods=["issue_tree"],
        expected_output="Analytical report plan with targeted research branches.",
        children=buckets,
    )


def _hypotheses(
    analysis: AnalysisOutput | None,
    report: FinalReport | None,
) -> list[CompetingHypothesis]:
    out: list[CompetingHypothesis] = []
    if report and report.executive_summary.main_answer:
        out.append(
            CompetingHypothesis(
                id="h_base",
                statement=report.executive_summary.main_answer,
                why_plausible="This is the current synthesized answer.",
                would_be_supported_by=["Additional high-quality sources confirming the same direction."],
                would_be_weakened_by=["Critical conflicts, source bias, or failed number verification."],
                current_confidence="medium",
            )
        )
    if analysis is not None:
        for i, conflict in enumerate(analysis.conflicts[:4], start=1):
            out.append(
                CompetingHypothesis(
                    id=f"h_conflict_{i}",
                    statement=f"{conflict.topic}: {conflict.claim_b or conflict.claim_a}",
                    why_plausible="A material source offers a divergent claim.",
                    would_be_supported_by=[conflict.claim_b or conflict.claim_a],
                    would_be_weakened_by=[conflict.resolution_hint or "Primary-source verification."],
                    current_confidence="unknown",
                )
            )
        for i, gap in enumerate(analysis.gaps[:3], start=1):
            out.append(
                CompetingHypothesis(
                    id=f"h_gap_{i}",
                    statement=f"The current answer may change after resolving: {gap.topic}",
                    why_plausible=gap.why_critical,
                    would_be_supported_by=[gap.what_to_find],
                    would_be_weakened_by=["Follow-up research shows the gap is immaterial."],
                    current_confidence="low",
                )
            )
    if not out:
        out.append(
            CompetingHypothesis(
                id="h_unknown",
                statement="The evidence is insufficient to choose a single answer.",
                why_plausible="No analysis output or synthesized answer is available.",
                would_be_supported_by=["Thin source base, unresolved gaps, or no numeric facts."],
                would_be_weakened_by=["Triangulated sources and verified key numbers."],
            )
        )
    return out


def _evidence_probes(analysis: AnalysisOutput | None) -> list[EvidenceProbe]:
    if analysis is None:
        return [
            EvidenceProbe(
                id="probe_missing_analysis",
                method="source_triangulation",
                target="analysis_output",
                question="What source-backed claims exist, and which claims are unsupported?",
                expected_evidence="Consensus, conflicts, gaps, and verified facts.",
            )
        ]
    probes: list[EvidenceProbe] = []
    for i, gap in enumerate(analysis.gaps[:5], start=1):
        probes.append(
            EvidenceProbe(
                id=f"probe_gap_{i}",
                method="key_assumptions_check",
                target=gap.topic,
                question=f"What assumption fails if we cannot find: {gap.what_to_find}?",
                expected_evidence=gap.what_to_find,
                disconfirming=True,
            )
        )
    for i, conflict in enumerate(analysis.conflicts[:5], start=1):
        probes.append(
            EvidenceProbe(
                id=f"probe_conflict_{i}",
                method="disconfirming_evidence",
                target=conflict.topic,
                question=f"What primary evidence would prove {conflict.source_a} wrong?",
                expected_evidence=conflict.resolution_hint or "Primary-source adjudication.",
                disconfirming=True,
            )
        )
    for i, number in enumerate(analysis.unverified_numbers[:5], start=1):
        probes.append(_number_probe(i, number))
    return probes


def _research_leads(
    question: str,
    *,
    domain_hint: str,
    analysis: AnalysisOutput | None,
    report: FinalReport | None,
    limit: int,
) -> list[ResearchLead]:
    leads: list[ResearchLead] = []
    authority_lead = _authority_lead(question, domain_hint=domain_hint, report=report)
    if authority_lead is not None:
        leads.append(authority_lead)
    leads.extend(_unsupported_claim_leads(domain_hint=domain_hint, analysis=analysis, report=report))
    if analysis is not None:
        for i, gap in enumerate(analysis.gaps, start=1):
            leads.append(
                ResearchLead(
                    id=f"gap_{i}",
                    kind="close_gap",
                    priority="must",
                    prompt=_gap_prompt(gap.topic, gap.what_to_find, gap.candidate_sources),
                    rationale=gap.why_critical,
                    candidate_sources=gap.candidate_sources,
                    recommended_service=_service_for(domain_hint, gap.candidate_sources),
                    recommended_mode=_mode_for("close_gap", domain_hint),
                    linked_to=[f"gap:{gap.topic}"],
                )
            )
        for i, conflict in enumerate(analysis.conflicts, start=1):
            leads.append(
                ResearchLead(
                    id=f"conflict_{i}",
                    kind="resolve_conflict",
                    priority="must" if conflict.importance == "critical" else "should",
                    prompt=(
                        f"Resolve this conflict with primary or highest-quality sources: "
                        f"{conflict.topic}. Claim A: {conflict.claim_a}. "
                        f"Claim B: {conflict.claim_b}. Find which scope, date, "
                        f"definition, or source bias explains the divergence."
                    ),
                    rationale=conflict.resolution_hint or "Conflicting evidence changes the answer.",
                    recommended_service=_service_for(domain_hint, []),
                    recommended_mode=_mode_for("resolve_conflict", domain_hint),
                    linked_to=[f"conflict:{conflict.topic}"],
                )
            )
        for i, number in enumerate(analysis.unverified_numbers, start=1):
            leads.append(_number_lead(i, number, domain_hint))

        anomaly_facts = _interesting_facts(analysis)
        for i, fact in enumerate(anomaly_facts[:4], start=1):
            leads.append(
                ResearchLead(
                    id=f"anomaly_{i}",
                    kind="explore_anomaly",
                    priority="should",
                    prompt=(
                        f"Investigate why this number matters and what explains it: "
                        f"{fact.value} {fact.metric} for {fact.subject}. Find context, "
                        f"historical comparison, peer benchmark, and counter-examples."
                    ),
                    rationale="A strong report follows surprising or decision-relevant numbers sideways.",
                    target_metrics=[fact.metric],
                    candidate_sources=[ref.url for ref in fact.sources if ref.url],
                    recommended_service=_service_for(domain_hint, []),
                    recommended_mode=_mode_for("explore_anomaly", domain_hint),
                    linked_to=[f"fact:{fact.fact_id}"],
                )
            )

    leads.append(
        ResearchLead(
            id="benchmark_1",
            kind="find_benchmark",
            priority="should",
            prompt=(
                f"For the question '{question}', find 3-5 relevant benchmarks: "
                f"historical baseline, peer group, global analogue, or adjacent-market comparator. "
                f"Return numbers, dates, source URLs, and explain comparability limits."
            ),
            rationale="Benchmarking turns isolated facts into interpretable evidence.",
            recommended_service=_service_for(domain_hint, []),
            recommended_mode=_mode_for("find_benchmark", domain_hint),
        )
    )
    leads.append(
        ResearchLead(
            id="disconfirm_1",
            kind="test_hypothesis",
            priority="should",
            prompt=(
                f"For the question '{question}', search specifically for evidence that would "
                f"make the current likely answer wrong. Prioritize primary sources, adverse cases, "
                f"failed analogies, and definitions that change the conclusion."
            ),
            rationale="Disconfirming research is the fastest way to avoid a polished but false answer.",
            recommended_service=_service_for(domain_hint, []),
            recommended_mode=_mode_for("test_hypothesis", domain_hint),
        )
    )
    return _dedupe_leads(leads)[:limit]


def _number_probe(index: int, number: UnverifiedNumber) -> EvidenceProbe:
    return EvidenceProbe(
        id=f"probe_number_{index}",
        method="number_verification",
        target=f"{number.value} {number.metric} {number.subject}",
        question=f"Can {number.value} be verified from a primary or authoritative source?",
        expected_evidence=number.why_unverified or "URL-backed number verification.",
    )


def _number_lead(index: int, number: UnverifiedNumber, domain_hint: str) -> ResearchLead:
    return ResearchLead(
        id=f"number_{index}",
        kind="verify_number",
        priority="must",
        prompt=(
            f"Verify this number: {number.value} for metric '{number.metric}' "
            f"and subject '{number.subject}'. Find the original source, exact date, "
            f"definition, unit, and whether another source contradicts it."
        ),
        rationale=number.why_unverified or "Unverified numbers cannot support a paid report.",
        target_metrics=[number.metric],
        recommended_service=_service_for(domain_hint, []),
        recommended_mode=_mode_for("verify_number", domain_hint),
        linked_to=[f"unverified:{number.metric}:{number.subject}"],
    )


def _service_for(domain_hint: str, candidate_sources: list[str]) -> ResearchService:
    joined_sources = " ".join(candidate_sources).lower()
    if domain_hint in {"financial_us", "medical_clinical", "scientific"}:
        return "valyu"
    if domain_hint == "legal_regulatory" and _has(joined_sources, "sec.gov", "fda.gov", "fred"):
        return "valyu"
    if domain_hint == "russian_market":
        return "perplexity"
    if domain_hint == "market_general":
        return "openai"
    return "perplexity"


def _mode_for(kind: ResearchLeadKind, domain_hint: str) -> str:
    if kind in {"resolve_conflict", "test_hypothesis"}:
        return "heavy" if domain_hint in {"financial_us", "medical_clinical"} else "standard"
    if kind == "verify_number":
        return "standard"
    return "standard"


def _benchmark_questions(question: str, domain_hint: str) -> list[str]:
    return [
        f"What is the historical baseline for the main metric in: {question}?",
        "Which peer group is comparable, and where does comparability break?",
        "Which global or adjacent-market analogue changes interpretation?",
        f"Which benchmark sources are strongest for domain '{domain_hint}'?",
    ]


def _authority_lead(
    question: str,
    *,
    domain_hint: str,
    report: FinalReport | None,
    minimum: int = 3,
) -> ResearchLead | None:
    if report is not None and count_authoritative_sources(report) >= minimum:
        return None
    sources = _authority_candidate_sources(domain_hint)
    return ResearchLead(
        id="authority_sources",
        kind="strengthen_source_base",
        priority="must",
        prompt=(
            f"Strengthen the source base for this report question: {question}. "
            f"Find at least {minimum} primary, official, regulatory, statistical, "
            "or top-tier domain sources that directly support the main answer. "
            "Return exact URLs, publication dates, the specific facts each source "
            "supports, and note any source that contradicts the current conclusion."
        ),
        rationale=(
            "Paid-ready reports require primary or authoritative sources, not only "
            "media summaries or aggregator pages."
        ),
        candidate_sources=sources,
        recommended_service=_service_for(domain_hint, sources),
        recommended_mode=_mode_for("strengthen_source_base", domain_hint),
        linked_to=["source_authority"],
    )


def _authority_candidate_sources(domain_hint: str) -> list[str]:
    if domain_hint == "russian_market":
        return [
            "cbr.ru",
            "dom.rf",
            "наш.дом.рф",
            "mos.ru",
            "erzrf.ru",
            "metrium.ru/research/",
            "rosstat.gov.ru",
        ]
    if domain_hint == "legal_regulatory":
        return ["europa.eu", "eur-lex.europa.eu", "ec.europa.eu", "official government portals"]
    if domain_hint == "financial_us":
        return ["sec.gov", "investor relations filings", "fred.stlouisfed.org", "bls.gov"]
    if domain_hint == "medical_clinical":
        return ["pubmed.ncbi.nlm.nih.gov", "clinicaltrials.gov", "fda.gov", "ema.europa.eu"]
    if domain_hint == "scientific":
        return ["peer-reviewed journals", "arxiv.org with peer-reviewed follow-up", "official benchmark datasets"]
    return ["official statistics", "regulatory sources", "primary company documents", "top-tier research reports"]


def _unsupported_claim_leads(
    *,
    domain_hint: str,
    analysis: AnalysisOutput | None,
    report: FinalReport | None,
    limit: int = 3,
) -> list[ResearchLead]:
    if report is None:
        return []
    audit = assess_evidence_support(report, analysis)
    leads: list[ResearchLead] = []
    candidate_sources = _authority_candidate_sources(domain_hint)
    for item in audit.claim_audits:
        if item.status != "unsupported":
            continue
        lead_id = re.sub(r"[^a-z0-9_]+", "_", item.origin.lower())[:36].strip("_")
        leads.append(
            ResearchLead(
                id=f"support_{lead_id or len(leads) + 1}",
                kind="support_claim",
                priority="must",
                prompt=(
                    "Find source evidence that supports, qualifies, or disproves this "
                    f"client-facing conclusion from {item.origin}: {item.claim}. "
                    "Return exact URLs, dates, numbers or quoted facts, and say whether "
                    "the claim should remain, be softened, or be removed."
                ),
                rationale=(
                    "The current client-facing report contains an unsupported conclusion; "
                    "paid delivery requires either source backing or removal."
                ),
                candidate_sources=candidate_sources,
                recommended_service=_service_for(domain_hint, candidate_sources),
                recommended_mode=_mode_for("support_claim", domain_hint),
                linked_to=[f"unsupported:{item.origin}"],
            )
        )
        if len(leads) >= limit:
            break
    return leads


def _monitoring_indicators(
    analysis: AnalysisOutput | None,
    report: FinalReport | None,
) -> list[str]:
    indicators: list[str] = []
    if analysis is not None:
        indicators.extend(f"Track gap closure: {gap.topic}" for gap in analysis.gaps[:4])
        indicators.extend(
            f"Track conflict resolution: {conflict.topic}" for conflict in analysis.conflicts[:4]
        )
        indicators.extend(f"Refresh metric: {fact.metric} / {fact.subject}" for fact in _numeric_facts(analysis)[:4])
    if report is not None and report.executive_summary.key_numbers:
        indicators.extend(
            f"Refresh key number: {item.metric} / {item.subject}"
            for item in report.executive_summary.key_numbers[:4]
        )
    return indicators or ["Track whether new evidence changes the main answer."]


def _interesting_facts(analysis: AnalysisOutput) -> list[NumericFact]:
    facts = _numeric_facts(analysis)
    scored = sorted(facts, key=lambda fact: (_number_density_score(fact), len(fact.sources)), reverse=True)
    return scored


def _numeric_facts(analysis: AnalysisOutput) -> list[NumericFact]:
    return list(analysis.high_relevance_facts or analysis.all_numeric_facts)


def _number_density_score(fact: NumericFact) -> int:
    text = " ".join([fact.value, fact.metric, fact.subject, fact.timeframe or ""])
    return len(re.findall(r"\d", text))


def _gap_prompt(topic: str, what_to_find: str, candidate_sources: list[str]) -> str:
    sources = ", ".join(candidate_sources) if candidate_sources else "best available primary sources"
    return (
        f"Close this evidence gap: {topic}. Find: {what_to_find}. "
        f"Use {sources}. Return exact numbers, definitions, dates, and URLs."
    )


def _parent_for_lead(lead: ResearchLead) -> str:
    if lead.kind in {"verify_number", "close_gap"}:
        return "evidence_base"
    if lead.kind == "support_claim":
        return "evidence_base"
    if lead.kind in {"resolve_conflict", "test_hypothesis"}:
        return "hypotheses"
    if lead.kind == "find_benchmark":
        return "benchmarks"
    if lead.kind == "strengthen_source_base":
        return "evidence_base"
    return "decision"


def _methods_for_lead(lead: ResearchLead) -> list[AnalyticMethod]:
    mapping: dict[ResearchLeadKind, list[AnalyticMethod]] = {
        "close_gap": ["key_assumptions_check", "source_triangulation"],
        "resolve_conflict": ["competing_hypotheses", "disconfirming_evidence"],
        "verify_number": ["number_verification", "source_triangulation"],
        "explore_anomaly": ["key_assumptions_check", "benchmarking"],
        "find_benchmark": ["benchmarking"],
        "strengthen_source_base": ["source_triangulation"],
        "support_claim": ["source_triangulation", "disconfirming_evidence"],
        "test_hypothesis": ["competing_hypotheses", "disconfirming_evidence"],
        "monitor_indicator": ["indicator_signpost"],
    }
    return mapping[lead.kind]


def _expected_output_for_lead(lead: ResearchLead) -> str:
    if lead.kind == "verify_number":
        return "Verified number with original URL, date, definition, and contradiction check."
    if lead.kind == "resolve_conflict":
        return "Adjudication note explaining which claim is stronger and why."
    if lead.kind == "find_benchmark":
        return "Benchmark table with comparability limits."
    if lead.kind == "strengthen_source_base":
        return "Authority source pack with exact URLs and supported claims."
    if lead.kind == "support_claim":
        return "Claim support note with keep/soften/remove recommendation."
    return "Source-backed evidence usable in report tables and appendices."


def _dedupe_leads(leads: list[ResearchLead]) -> list[ResearchLead]:
    seen: set[str] = set()
    out: list[ResearchLead] = []
    for lead in leads:
        key = re.sub(r"\W+", " ", lead.prompt.lower()).strip()[:180]
        if key in seen:
            continue
        seen.add(key)
        out.append(lead)
    return out


def _combined_text(
    question: str,
    report: FinalReport | None,
    analysis: AnalysisOutput | None,
) -> str:
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
    if analysis is not None:
        chunks.extend(gap.topic for gap in analysis.gaps)
        chunks.extend(conflict.topic for conflict in analysis.conflicts)
        chunks.extend(fact.subject for fact in analysis.high_relevance_facts[:20])
    return " ".join(chunks).lower()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _has(text: str, *needles: str) -> bool:
    return any(needle.lower() in text for needle in needles)


InquiryNode.model_rebuild()
