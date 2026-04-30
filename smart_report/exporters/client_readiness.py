"""Client export readiness checks.

These gates are deliberately stricter than unit-test validity. A report can be
schema-valid and still be unacceptable as a paid client artefact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import AnalysisOutput, FinalReport
from ..source_authority import count_authoritative_sources
from .client_view import contains_client_leak


@dataclass(frozen=True)
class ReadinessIssue:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ClientReadiness:
    ready: bool
    score: int
    issues: list[ReadinessIssue] = field(default_factory=list)

    def model_dump(self) -> dict:
        return {
            "ready": self.ready,
            "score": self.score,
            "issues": [issue.__dict__ for issue in self.issues],
        }


def assess_client_readiness(
    report: FinalReport,
    *,
    client_report: FinalReport | None = None,
    analysis: AnalysisOutput | None = None,
    min_authoritative_sources: int = 2,
    min_numeric_facts: int = 20,
) -> ClientReadiness:
    """Return whether *report* is safe to export as a finished client report."""

    issues: list[ReadinessIssue] = []
    metadata = report.metadata or {}

    authoritative_count = count_authoritative_sources(client_report or report)
    if (
        metadata.get("evidence_quality") == "LOW_EVIDENCE_QUALITY"
        and authoritative_count < min_authoritative_sources
    ):
        issues.append(
            ReadinessIssue(
                "low_evidence_quality",
                "critical",
                "Evidence quality is LOW; authoritative source threshold was not met.",
            )
        )

    source_count = len(report.all_sources)
    if source_count < min_authoritative_sources:
        issues.append(
            ReadinessIssue(
                "too_few_sources",
                "critical",
                f"Report has {source_count} sources; minimum is {min_authoritative_sources}.",
            )
        )

    if authoritative_count < min_authoritative_sources:
        issues.append(
            ReadinessIssue(
                "too_few_authoritative_sources",
                "critical",
                (
                    f"Report has {authoritative_count} authoritative source(s); "
                    f"minimum is {min_authoritative_sources}."
                ),
            )
        )

    gap_counts = metadata.get("gap_count_by_severity") or {}
    critical_gaps = int(gap_counts.get("critical") or 0)
    if critical_gaps:
        issues.append(
            ReadinessIssue(
                "critical_gaps_open",
                "critical",
                f"Report still has {critical_gaps} critical evidence gap(s).",
            )
        )

    facts_total = 0
    if analysis is not None:
        facts_total = len(analysis.high_relevance_facts or analysis.all_numeric_facts)
    if facts_total < min_numeric_facts:
        issues.append(
            ReadinessIssue(
                "insufficient_fact_table",
                "major",
                f"Only {facts_total} numeric fact(s) available; minimum is {min_numeric_facts}.",
            )
        )

    lint = metadata.get("language_lint") or {}
    lint_count = int(lint.get("warnings_count") or 0)
    if lint_count and client_report is None:
        issues.append(
            ReadinessIssue(
                "language_lint_warnings",
                "major",
                f"Language lint reports {lint_count} warning(s) on the raw report.",
            )
        )

    leaks = contains_client_leak(client_report or report)
    if leaks:
        issues.append(
            ReadinessIssue(
                "client_leaks",
                "critical",
                "Client-facing text still contains internal markers: " + ", ".join(sorted(set(leaks))),
            )
        )

    critical = sum(1 for issue in issues if issue.severity == "critical")
    major = sum(1 for issue in issues if issue.severity == "major")
    score = max(0, 10 - critical * 3 - major)
    return ClientReadiness(ready=critical == 0 and major == 0, score=score, issues=issues)
