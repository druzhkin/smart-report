"""Heuristic evidence-support audit for client-facing conclusions.

This is not a truth oracle. It checks whether the report's visible conclusions
carry enough evidence signals to be defensible in a paid delivery package:
citations, numeric fact backing, qualitative fact backing, and explicit source
links from the analysis layer. The goal is to expose weakly supported
conclusions before export.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import AnalysisOutput, FinalReport

EvidenceClaimStatus = Literal["supported", "partial", "unsupported"]


class _EvidenceBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceClaimAudit(_EvidenceBase):
    claim: str
    origin: str
    status: EvidenceClaimStatus
    score: int
    citation_markers: int = 0
    source_links: int = 0
    numeric_matches: int = 0
    qualitative_matches: int = 0
    has_number: bool = False
    missing_signals: list[str] = Field(default_factory=list)


class EvidenceAuditReport(_EvidenceBase):
    overall_score: int
    claim_count: int
    supported: int
    partial: int
    unsupported: int
    source_count: int
    numeric_fact_count: int
    claim_audits: list[EvidenceClaimAudit]
    summary: str


def assess_evidence_support(
    report: FinalReport,
    analysis: AnalysisOutput | None = None,
) -> EvidenceAuditReport:
    """Score whether major conclusions have visible evidence support."""

    claims = _extract_claims(report, analysis)
    numeric_facts = list((analysis.high_relevance_facts or analysis.all_numeric_facts) if analysis else [])
    qualitative_facts = list(analysis.all_qualitative_facts if analysis else [])
    audits = [
        _score_claim(
            claim=claim,
            origin=origin,
            source_links=source_links,
            numeric_facts=numeric_facts,
            qualitative_facts=qualitative_facts,
        )
        for origin, claim, source_links in claims
    ]
    counts = Counter(item.status for item in audits)
    overall = round(sum(item.score for item in audits) / len(audits)) if audits else 0
    return EvidenceAuditReport(
        overall_score=overall,
        claim_count=len(audits),
        supported=counts["supported"],
        partial=counts["partial"],
        unsupported=counts["unsupported"],
        source_count=len(report.all_sources or []),
        numeric_fact_count=len(numeric_facts),
        claim_audits=audits,
        summary=_summary(overall, counts, len(audits)),
    )


def _extract_claims(
    report: FinalReport,
    analysis: AnalysisOutput | None,
) -> list[tuple[str, str, int]]:
    claims: list[tuple[str, str, int]] = []
    if report.executive_summary.main_answer:
        claims.append(("executive_summary.main_answer", report.executive_summary.main_answer, 0))
    for idx, finding in enumerate(report.executive_summary.top_findings, start=1):
        claims.append((f"executive_summary.top_findings[{idx}]", finding, 0))
    for idx, item in enumerate(report.key_numbers_highlight, start=1):
        text = f"{item.value} {item.label}".strip()
        claims.append((f"key_numbers_highlight[{idx}]", text, 1 if item.source_ref else 0))
    for idx, item in enumerate(report.ranking, start=1):
        claims.append((f"ranking[{idx}]", item.rationale, 0))
    for idx, item in enumerate(report.callouts, start=1):
        claims.append((f"callouts[{idx}]", f"{item.title}. {item.body}", 0))
    if analysis:
        for idx, item in enumerate(analysis.consensus, start=1):
            claims.append((f"analysis.consensus[{idx}]", item.claim, len(item.supporting_sources)))
    return [
        (origin, _compact(claim), source_links)
        for origin, claim, source_links in claims
        if _compact(claim)
    ]


def _score_claim(
    *,
    claim: str,
    origin: str,
    source_links: int,
    numeric_facts: list,
    qualitative_facts: list,
) -> EvidenceClaimAudit:
    citation_markers = len(re.findall(r"(?:\[\d+\]|\[REF:[^\]]+\])", claim))
    has_number = bool(_number_tokens(claim) or re.search(r"[\u2080-\u2089]", claim))
    numeric_matches = _numeric_matches(claim, numeric_facts)
    qualitative_matches = _qualitative_matches(claim, qualitative_facts)
    analysis_source_links = source_links + qualitative_matches
    score = 0
    missing: list[str] = []

    if citation_markers:
        score += min(60, citation_markers * 35)
    else:
        missing.append("No inline citation marker is visible on this conclusion.")

    if analysis_source_links:
        score += min(35, analysis_source_links * 35)
    else:
        missing.append("No explicit supporting source link from the analysis layer.")

    if has_number:
        if numeric_matches:
            score += min(35, numeric_matches * 35)
        else:
            missing.append("Conclusion contains a number but no matching numeric fact was found.")
    else:
        score += 10

    score = min(100, score)
    if score >= 70:
        status: EvidenceClaimStatus = "supported"
    elif score >= 35:
        status = "partial"
    else:
        status = "unsupported"

    return EvidenceClaimAudit(
        claim=claim,
        origin=origin,
        status=status,
        score=score,
        citation_markers=citation_markers,
        source_links=source_links,
        numeric_matches=numeric_matches,
        qualitative_matches=qualitative_matches,
        has_number=has_number,
        missing_signals=missing,
    )


def _numeric_matches(claim: str, numeric_facts: list) -> int:
    normalized_claim = _normalize_number_text(claim)
    claim_numbers = _number_tokens(claim)
    matches = 0
    for fact in numeric_facts:
        value = _normalize_number_text(str(getattr(fact, "value", "")))
        metric = str(getattr(fact, "metric", "") or "").lower()
        subject = str(getattr(fact, "subject", "") or "").lower()
        if value and value in normalized_claim:
            matches += 1
            continue
        if metric and metric in claim.lower() and subject and subject in claim.lower():
            matches += 1
            continue
        fact_numbers = _number_tokens(str(getattr(fact, "value", "")))
        if fact_numbers and len(claim_numbers.intersection(fact_numbers)) >= min(2, len(fact_numbers)):
            matches += 1
    return matches


def _qualitative_matches(claim: str, qualitative_facts: list) -> int:
    claim_tokens = _meaningful_tokens(claim)
    if len(claim_tokens) < 3:
        return 0

    matches = 0
    for fact in qualitative_facts:
        if not getattr(fact, "sources", None):
            continue
        text = " ".join(
            [
                str(getattr(fact, "statement", "") or ""),
                str(getattr(fact, "subject", "") or ""),
            ]
        )
        fact_tokens = _meaningful_tokens(text)
        if not fact_tokens:
            continue
        overlap = claim_tokens.intersection(fact_tokens)
        required = max(3, min(6, round(min(len(claim_tokens), len(fact_tokens)) * 0.28)))
        if len(overlap) >= required:
            matches += 1
    return matches


def _normalize_number_text(value: str) -> str:
    return (
        value.lower()
        .replace(",", ".")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u2082", "2")
        .replace(" ", "")
    )


def _number_tokens(value: str) -> set[str]:
    normalized = (
        value.lower()
        .replace(",", ".")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u2082", "2")
    )
    return {
        match.group(0)
        for match in re.finditer(r"(?<![^\W\d_])\d+(?:\.\d+)?(?![^\W\d_])", normalized)
    }


def _meaningful_tokens(value: str) -> set[str]:
    normalized = re.sub(r"[^\w]+", " ", value.lower())
    stopwords = {
        "and", "the", "for", "with", "that", "this", "from", "into", "under", "than",
        "or", "not", "are", "was", "were", "will", "should", "could", "would",
    }
    return {
        token
        for token in normalized.split()
        if len(token) >= 4 and not token.isdigit() and token not in stopwords
    }


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _summary(score: int, counts: Counter, claim_count: int) -> str:
    if claim_count == 0:
        return "No client-facing conclusions were available for evidence-support auditing."
    return (
        f"Evidence support score {score}/100 across {claim_count} conclusion(s): "
        f"{counts['supported']} supported, {counts['partial']} partial, "
        f"{counts['unsupported']} unsupported."
    )
