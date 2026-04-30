from __future__ import annotations

from smart_report.adjudication_audit import assess_adjudication_quality
from smart_report.models import AnalysisOutput, Conflict, ExecutiveSummaryV4, FinalReport


def test_adjudication_audit_scores_resolved_conflict():
    report = FinalReport(
        session_id="adjudication",
        question="Resolve conflicting market claims",
        executive_summary=ExecutiveSummaryV4(main_answer="On balance, source A is stronger."),
        conflicts_section=(
            "Forecast conflict between Source A and Source B is resolved on balance: "
            "Source A is more reliable within the stated scope, while Source B is a scenario limitation."
        ),
    )
    analysis = AnalysisOutput(
        conflicts=[
            Conflict(
                topic="Forecast conflict",
                source_a="Source A",
                claim_a="High growth",
                source_b="Source B",
                claim_b="Low growth",
                resolution_hint="Source A has stronger primary data.",
                importance="critical",
            )
        ]
    )

    audit = assess_adjudication_quality(report, analysis)

    assert audit.overall_score >= 75
    assert audit.resolved == 1
    assert audit.critical_unresolved == 0


def test_adjudication_audit_flags_unresolved_critical_conflict():
    report = FinalReport(
        session_id="adjudication",
        question="Resolve conflicting market claims",
        executive_summary=ExecutiveSummaryV4(main_answer="The market will grow."),
        conflicts_section="Some sources disagree.",
    )
    analysis = AnalysisOutput(
        conflicts=[
            Conflict(
                topic="Forecast conflict",
                source_a="Source A",
                claim_a="High growth",
                source_b="Source B",
                claim_b="Low growth",
                importance="critical",
            )
        ]
    )

    audit = assess_adjudication_quality(report, analysis)

    assert audit.overall_score < 45
    assert audit.unresolved == 1
    assert audit.critical_unresolved == 1
    assert audit.conflict_audits[0].missing_signals
