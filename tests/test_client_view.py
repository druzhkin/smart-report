from smart_report.exporters.client_readiness import assess_client_readiness
from smart_report.exporters.client_view import contains_client_leak, sanitize_final_report
from smart_report.models import (
    ExecutiveSummaryV4,
    FinalReport,
    NumberedSource,
    RankingItem,
    Source,
    SourceRef,
)


def test_sanitize_final_report_removes_pipeline_language():
    report = FinalReport(
        session_id="s1",
        question="Q",
        executive_summary=ExecutiveSummaryV4(
            main_answer=(
                "[STRONG] Базовая линия 561 тыс. [REF:https://example.com/a]. "
                "Это разрешает конфликт первого раунда между 542 и 887 тыс."
            ),
            top_findings=[
                "[MODERATE] Ставка важна [REF:https://example.com/a].",
                "Подробнее: Раздел main_synthesis",
            ],
        ),
        main_synthesis="[WEAK] Вывод по рынку [REF:https://example.com/a].",
        conflicts_section="Perplexity спутал сегменты. Клиентский вывод должен быть чистым.",
        all_sources=[
            Source(title="Example", url="https://example.com/a", tool="perplexity", reliability="high")
        ],
        bibliography=[
            NumberedSource(
                number=1,
                source_ref=SourceRef(url="https://example.com/a", title="Example"),
            )
        ],
    )

    clean = sanitize_final_report(report)
    dumped = str(clean.model_dump(mode="json"))
    text_values = " ".join(
        str(v)
        for v in [
            clean.executive_summary.main_answer,
            *clean.executive_summary.top_findings,
            clean.main_synthesis,
            clean.conflicts_section,
        ]
    )

    assert "[STRONG]" not in dumped
    assert "[MODERATE]" not in dumped
    assert "[WEAK]" not in dumped
    assert "[REF:" not in dumped
    assert "первого раунда" not in dumped
    assert "main_synthesis" not in text_values
    assert "Perplexity" not in text_values
    assert "[1]" in dumped
    assert contains_client_leak(clean) == []
    assert clean.metadata == {"client_view_sanitized": True}


def test_client_readiness_blocks_low_evidence_report():
    report = FinalReport(
        session_id="s1",
        question="Q",
        executive_summary=ExecutiveSummaryV4(main_answer="Готовый вывод."),
        metadata={
            "evidence_quality": "LOW_EVIDENCE_QUALITY",
            "gap_count_by_severity": {"critical": 1, "moderate": 0, "minor": 0},
            "language_lint": {"warnings_count": 2},
        },
    )

    clean = sanitize_final_report(report)
    readiness = assess_client_readiness(report, client_report=clean)

    assert readiness.ready is False
    assert readiness.score < 8
    assert {issue.code for issue in readiness.issues} >= {
        "low_evidence_quality",
        "too_few_sources",
        "critical_gaps_open",
        "insufficient_fact_table",
    }
    assert "language_lint_warnings" not in {issue.code for issue in readiness.issues}


def test_client_readiness_uses_raw_language_lint_only_without_client_copy():
    report = FinalReport(
        session_id="s1",
        question="Q",
        executive_summary=ExecutiveSummaryV4(main_answer="Ready answer."),
        metadata={"language_lint": {"warnings_count": 2}},
    )

    readiness = assess_client_readiness(report)

    assert "language_lint_warnings" in {issue.code for issue in readiness.issues}


def test_client_readiness_recomputes_low_evidence_gate_from_authoritative_sources():
    report = FinalReport(
        session_id="s1",
        question="Q",
        executive_summary=ExecutiveSummaryV4(main_answer="Ready answer."),
        all_sources=[
            Source(
                title="European Commission official source",
                url="https://climate.ec.europa.eu/news",
                reliability="medium",
            ),
            Source(
                title="European Parliament briefing",
                url="https://www.europarl.europa.eu/thinktank/en/document/x",
                reliability="medium",
            ),
        ],
        metadata={"evidence_quality": "LOW_EVIDENCE_QUALITY"},
    )
    clean = sanitize_final_report(report)

    readiness = assess_client_readiness(report, client_report=clean, min_numeric_facts=0)

    assert "low_evidence_quality" not in {issue.code for issue in readiness.issues}
    assert "too_few_authoritative_sources" not in {issue.code for issue in readiness.issues}


def test_sanitize_final_report_preserves_structured_literal_fields():
    report = FinalReport(
        session_id="s1",
        question="Q",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer."),
        all_sources=[
            Source(title="Medium source", url="https://example.com/m", reliability="medium"),
            Source(title="Low source", url="https://example.com/l", reliability="low"),
        ],
        ranking=[
            RankingItem(
                label="Option A",
                rationale="Medium evidence remains valid structured data.",
                evidence_strength="medium",
            )
        ],
    )

    clean = sanitize_final_report(report)

    assert [source.reliability for source in clean.all_sources] == ["medium", "low"]
    assert clean.ranking[0].evidence_strength == "medium"
