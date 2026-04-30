"""Conflict adjudication audit for premium analytical reports.

Paid analytical work should not merely list disagreements. It should show
which conflicts matter, whether they were resolved, and what logic or scope
limits the conclusion. This module scores that layer heuristically.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import AnalysisOutput, Conflict, FinalReport

AdjudicationStatus = Literal["resolved", "bracketed", "unresolved"]


class _AdjudicationBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConflictAdjudication(_AdjudicationBase):
    topic: str
    importance: str
    status: AdjudicationStatus
    score: int
    evidence_signals: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    recommendation: str = ""


class AdjudicationAuditReport(_AdjudicationBase):
    overall_score: int
    conflict_count: int
    resolved: int
    bracketed: int
    unresolved: int
    critical_unresolved: int
    conflict_audits: list[ConflictAdjudication]
    summary: str


def assess_adjudication_quality(
    report: FinalReport,
    analysis: AnalysisOutput | None = None,
) -> AdjudicationAuditReport:
    conflicts = list(analysis.conflicts if analysis else [])
    audits = [_score_conflict(conflict, report) for conflict in conflicts]
    counts = Counter(item.status for item in audits)
    critical_unresolved = sum(
        1 for item in audits if item.importance == "critical" and item.status == "unresolved"
    )
    overall = round(sum(item.score for item in audits) / len(audits)) if audits else 100
    return AdjudicationAuditReport(
        overall_score=overall,
        conflict_count=len(audits),
        resolved=counts["resolved"],
        bracketed=counts["bracketed"],
        unresolved=counts["unresolved"],
        critical_unresolved=critical_unresolved,
        conflict_audits=audits,
        summary=_summary(overall, counts, len(audits), critical_unresolved),
    )


def _score_conflict(conflict: Conflict, report: FinalReport) -> ConflictAdjudication:
    text = _report_text(report)
    lowered = text.lower()
    signals: list[str] = []
    missing: list[str] = []
    score = 0

    topic_hits = _hits(conflict.topic, lowered)
    source_a_hits = _hits(conflict.source_a, lowered)
    source_b_hits = _hits(conflict.source_b, lowered)
    if topic_hits:
        score += 20
        signals.append("topic_discussed")
    else:
        missing.append("Conflict topic is not visibly discussed in the client report.")
    if source_a_hits and source_b_hits:
        score += 20
        signals.append("both_sides_named")
    else:
        missing.append("Both conflicting sides/sources are not visibly named.")

    if conflict.resolution_hint:
        score += 20
        signals.append("analysis_resolution_hint")
    else:
        missing.append("Analyzer provided no resolution hint.")

    adjudication_language = _has_adjudication_language(lowered)
    limitation_language = _has_limitation_language(lowered)
    if adjudication_language:
        score += 25
        signals.append("adjudication_language")
    else:
        missing.append("Report lacks explicit adjudication language.")
    if limitation_language:
        score += 15
        signals.append("scope_or_limitation_language")

    score = min(100, score)
    if score >= 75:
        status: AdjudicationStatus = "resolved"
    elif score >= 45:
        status = "bracketed"
    else:
        status = "unresolved"

    return ConflictAdjudication(
        topic=conflict.topic,
        importance=conflict.importance,
        status=status,
        score=score,
        evidence_signals=signals,
        missing_signals=missing,
        recommendation=_recommendation(status, conflict.importance),
    )


def _report_text(report: FinalReport) -> str:
    parts = [
        report.executive_summary.main_answer,
        " ".join(report.executive_summary.top_findings),
        report.main_synthesis,
        report.consensus_section,
        report.conflicts_section,
        report.gaps_filled_section,
        " ".join(item.rationale for item in report.ranking),
        " ".join(f"{item.title} {item.body}" for item in report.callouts),
    ]
    return re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip()


def _hits(needle: str, haystack: str) -> bool:
    normalized = (needle or "").strip().lower()
    if not normalized:
        return False
    tokens = [token for token in re.findall(r"[\w.-]{3,}", normalized) if token]
    return normalized in haystack or any(token in haystack for token in tokens[:3])


def _has_adjudication_language(text: str) -> bool:
    return any(
        token in text
        for token in (
            "therefore",
            "on balance",
            "stronger evidence",
            "weaker evidence",
            "more reliable",
            "less reliable",
            "resolved",
            "adjudicat",
            "scope",
            "definition",
            "следовательно",
            "взвешенно",
            "более надеж",
            "менее надеж",
            "разреш",
            "границ",
            "определени",
        )
    )


def _has_limitation_language(text: str) -> bool:
    return any(
        token in text
        for token in (
            "limitation",
            "uncertain",
            "confidence",
            "depends on",
            "scenario",
            "scope",
            "огранич",
            "неопредел",
            "уверенн",
            "сценар",
            "зависит",
        )
    )


def _recommendation(status: AdjudicationStatus, importance: str) -> str:
    if status == "resolved":
        return "Carry the adjudication logic into the executive answer and data pack."
    if status == "bracketed":
        return "Make the scope, stronger evidence, and residual uncertainty explicit."
    if importance == "critical":
        return "Run targeted follow-up research before paid delivery; critical conflict is unresolved."
    return "Add a sourced resolution or bracket the conflict as an explicit limitation."


def _summary(score: int, counts: Counter, conflict_count: int, critical_unresolved: int) -> str:
    if conflict_count == 0:
        return "No conflicts were available for adjudication scoring."
    return (
        f"Adjudication score {score}/100 across {conflict_count} conflict(s): "
        f"{counts['resolved']} resolved, {counts['bracketed']} bracketed, "
        f"{counts['unresolved']} unresolved, {critical_unresolved} critical unresolved."
    )
