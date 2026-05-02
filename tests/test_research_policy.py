from smart_report.models import ExecutiveSummaryV4, FinalReport, Source
from smart_report.research_policy import assess_research_policy, recommended_service_for_policy


def test_research_policy_flags_missing_required_families():
    report = FinalReport(
        session_id="rp",
        question="EU AI Act regulatory impact on enterprise SaaS",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer."),
        all_sources=[
            Source(title="European Commission AI Act", url="https://ec.europa.eu/example"),
            Source(title="Industry blog", url="https://example.com/blog"),
        ],
    )

    assessment = assess_research_policy(report.question, report)

    assert assessment.domain == "eu_regulatory"
    assert assessment.passed is False
    assert assessment.tier1_count == 1
    assert "europa" in assessment.required_source_families
    assert assessment.issues


def test_research_policy_routes_academic_queries_to_paper_search():
    service = recommended_service_for_policy(
        "LLM observability benchmark methodology",
        ["arxiv papers", "academic benchmark", "github repository"],
    )

    assert service == "paper_search"
