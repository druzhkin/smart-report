"""Claim-to-evidence graph for report quality control.

This module is deliberately deterministic. It does not decide whether a claim is
true; it records whether a client-facing claim is visibly backed by citations,
numeric facts, qualitative facts, or explicit source links. The graph is used by
readiness gates, export audits, and the frontend inspection surface.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import AnalysisOutput, FinalReport, SourceRef

EvidenceNodeStatus = Literal["supported", "partial", "unsupported"]
EvidenceLinkKind = Literal["citation_marker", "numeric_fact", "qualitative_fact", "analysis_source"]


class _GraphBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceLink(_GraphBase):
    kind: EvidenceLinkKind
    source_url: str = ""
    source_title: str = ""
    fact_id: str = ""
    detail: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class ClaimEvidenceNode(_GraphBase):
    claim_id: str
    origin: str
    claim: str
    status: EvidenceNodeStatus
    score: int
    links: list[EvidenceLink] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    has_number: bool = False


class EvidenceGraphSummary(_GraphBase):
    score: int
    claim_count: int
    supported: int
    partial: int
    unsupported: int
    linked_source_count: int
    numeric_fact_links: int
    qualitative_fact_links: int


class EvidenceGraph(_GraphBase):
    summary: EvidenceGraphSummary
    nodes: list[ClaimEvidenceNode]


def build_evidence_graph(
    report: FinalReport,
    analysis: AnalysisOutput | None = None,
) -> EvidenceGraph:
    """Build a graph from visible report conclusions to available evidence."""

    claims = _extract_client_claims(report, analysis)
    numeric_facts = list((analysis.high_relevance_facts or analysis.all_numeric_facts) if analysis else [])
    qualitative_facts = list(analysis.all_qualitative_facts if analysis else [])
    nodes = [
        _score_node(
            claim_id=f"claim_{idx:03d}",
            origin=origin,
            claim=claim,
            source_labels=source_labels,
            numeric_facts=numeric_facts,
            qualitative_facts=qualitative_facts,
            bibliography=_bibliography_refs(report),
        )
        for idx, (origin, claim, source_labels) in enumerate(claims, start=1)
    ]
    counts = Counter(node.status for node in nodes)
    linked_sources = {
        link.source_url
        for node in nodes
        for link in node.links
        if link.source_url
    }
    score = round(sum(node.score for node in nodes) / len(nodes)) if nodes else 0
    return EvidenceGraph(
        summary=EvidenceGraphSummary(
            score=score,
            claim_count=len(nodes),
            supported=counts["supported"],
            partial=counts["partial"],
            unsupported=counts["unsupported"],
            linked_source_count=len(linked_sources),
            numeric_fact_links=sum(
                1 for node in nodes for link in node.links if link.kind == "numeric_fact"
            ),
            qualitative_fact_links=sum(
                1 for node in nodes for link in node.links if link.kind == "qualitative_fact"
            ),
        ),
        nodes=nodes,
    )


def _extract_client_claims(
    report: FinalReport,
    analysis: AnalysisOutput | None,
) -> list[tuple[str, str, list[str]]]:
    claims: list[tuple[str, str, list[str]]] = []
    if report.executive_summary.main_answer:
        claims.append(("executive_summary.main_answer", report.executive_summary.main_answer, []))
    for idx, finding in enumerate(report.executive_summary.top_findings, start=1):
        claims.append((f"executive_summary.top_findings[{idx}]", finding, []))
    for idx, number in enumerate(report.executive_summary.key_numbers, start=1):
        text = f"{number.value} {number.metric} {number.subject}".strip()
        claims.append((f"executive_summary.key_numbers[{idx}]", text, [number.source_url]))
    for idx, item in enumerate(report.key_numbers_highlight, start=1):
        text = f"{item.value} {item.label}".strip()
        claims.append((f"key_numbers_highlight[{idx}]", text, [item.source_ref]))
    for idx, item in enumerate(report.ranking, start=1):
        claims.append((f"ranking[{idx}]", item.rationale, []))
    for idx, item in enumerate(report.callouts, start=1):
        claims.append((f"callouts[{idx}]", f"{item.title}. {item.body}", []))
    if analysis:
        for idx, item in enumerate(analysis.consensus, start=1):
            claims.append((f"analysis.consensus[{idx}]", item.claim, item.supporting_sources))
    return [
        (origin, _compact(claim), [label for label in labels if label])
        for origin, claim, labels in claims
        if _compact(claim)
    ]


def _score_node(
    *,
    claim_id: str,
    origin: str,
    claim: str,
    source_labels: list[str],
    numeric_facts: list,
    qualitative_facts: list,
    bibliography: dict[str, SourceRef],
) -> ClaimEvidenceNode:
    links: list[EvidenceLink] = []
    missing: list[str] = []
    has_number = bool(_number_tokens(claim))

    citation_count = len(re.findall(r"(?:\[\d+\]|\[REF:[^\]]+\])", claim))
    for idx in range(citation_count):
        links.append(EvidenceLink(kind="citation_marker", detail=f"inline citation marker {idx + 1}"))
    if not citation_count:
        missing.append("No inline citation marker.")

    for label in source_labels:
        ref = _match_source(label, bibliography)
        links.append(
            EvidenceLink(
                kind="analysis_source",
                source_url=ref.url if ref else label,
                source_title=ref.title or "" if ref else "",
                detail=label,
                confidence="high" if ref and ref.confidence == "primary" else "medium",
            )
        )

    numeric_links = _numeric_links(claim, numeric_facts)
    links.extend(numeric_links)
    if has_number and not numeric_links:
        missing.append("Claim contains a number but no matching numeric fact.")

    qualitative_links = _qualitative_links(claim, qualitative_facts)
    links.extend(qualitative_links)
    if not source_labels and not qualitative_links:
        missing.append("No qualitative fact/source link from analysis.")

    score = min(
        100,
        citation_count * 25
        + len(source_labels) * 25
        + len(numeric_links) * 45
        + len(qualitative_links) * 20
        + (10 if not has_number else 0),
    )
    if score >= 70:
        status: EvidenceNodeStatus = "supported"
    elif score >= 35:
        status = "partial"
    else:
        status = "unsupported"
    return ClaimEvidenceNode(
        claim_id=claim_id,
        origin=origin,
        claim=claim,
        status=status,
        score=score,
        links=links,
        missing=missing,
        has_number=has_number,
    )


def _numeric_links(claim: str, facts: list) -> list[EvidenceLink]:
    claim_numbers = _number_tokens(claim)
    out: list[EvidenceLink] = []
    for fact in facts:
        fact_numbers = _number_tokens(str(getattr(fact, "value", "")))
        metric = str(getattr(fact, "metric", "") or "").lower()
        subject = str(getattr(fact, "subject", "") or "").lower()
        matched_number = bool(claim_numbers and fact_numbers and claim_numbers.intersection(fact_numbers))
        matched_label = bool(metric and metric in claim.lower() and subject and subject in claim.lower())
        if not (matched_number or matched_label):
            continue
        source = next(iter(getattr(fact, "sources", []) or []), None)
        out.append(
            EvidenceLink(
                kind="numeric_fact",
                source_url=getattr(source, "url", "") or "",
                source_title=getattr(source, "title", "") or "",
                fact_id=str(getattr(fact, "fact_id", "") or ""),
                detail=f"{getattr(fact, 'value', '')} {getattr(fact, 'metric', '')}".strip(),
                confidence="high" if getattr(source, "confidence", "") == "primary" else "medium",
            )
        )
    return out


def _qualitative_links(claim: str, facts: list) -> list[EvidenceLink]:
    claim_tokens = _tokens(claim)
    out: list[EvidenceLink] = []
    if len(claim_tokens) < 3:
        return out
    for fact in facts:
        source = next(iter(getattr(fact, "sources", []) or []), None)
        if source is None:
            continue
        fact_text = f"{getattr(fact, 'statement', '')} {getattr(fact, 'subject', '')}"
        overlap = claim_tokens.intersection(_tokens(fact_text))
        if len(overlap) < max(3, min(6, round(len(claim_tokens) * 0.25))):
            continue
        out.append(
            EvidenceLink(
                kind="qualitative_fact",
                source_url=getattr(source, "url", "") or "",
                source_title=getattr(source, "title", "") or "",
                fact_id=str(getattr(fact, "fact_id", "") or ""),
                detail=str(getattr(fact, "statement", "") or "")[:180],
                confidence="high" if getattr(source, "confidence", "") == "primary" else "medium",
            )
        )
    return out


def _bibliography_refs(report: FinalReport) -> dict[str, SourceRef]:
    refs: dict[str, SourceRef] = {}
    for item in report.bibliography or []:
        ref = item.source_ref
        for key in (str(item.number), ref.url, ref.title or ""):
            if key:
                refs[key.lower()] = ref
    return refs


def _match_source(label: str, refs: dict[str, SourceRef]) -> SourceRef | None:
    lowered = label.lower()
    if lowered in refs:
        return refs[lowered]
    for key, ref in refs.items():
        if key and (key in lowered or lowered in key):
            return ref
    return None


def _number_tokens(value: str) -> set[str]:
    normalized = str(value).replace(",", ".")
    return {match.group(0) for match in re.finditer(r"\d+(?:\.\d+)?", normalized)}


def _tokens(value: str) -> set[str]:
    stop = {"and", "the", "for", "with", "that", "this", "from", "into", "или", "для"}
    return {
        token
        for token in re.findall(r"[A-Za-zА-Яа-я0-9]+", str(value).lower())
        if len(token) >= 4 and not token.isdigit() and token not in stop
    }


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
