from smart_report.models import ExecutiveSummaryV4, FinalReport, NumberedSource, Source, SourceRef
from smart_report.source_authority import count_authoritative_sources


def test_authority_counts_high_reliability_and_official_domains():
    report = FinalReport(
        session_id="s",
        question="Q",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer."),
        all_sources=[
            Source(title="Industry blog", url="https://example.com/a", reliability="medium"),
            Source(title="European Commission rules", url="https://climate.ec.europa.eu/news", reliability="medium"),
            Source(title="Official statistics", url="https://stats.example.com", reliability="high"),
        ],
    )

    assert count_authoritative_sources(report) == 2


def test_authority_counts_primary_bibliography_refs():
    report = FinalReport(
        session_id="s",
        question="Q",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer."),
        bibliography=[
            NumberedSource(
                number=1,
                source_ref=SourceRef(
                    title="Primary filing",
                    url="https://example.com/filing",
                    confidence="primary",
                ),
            )
        ],
    )

    assert count_authoritative_sources(report) == 1
