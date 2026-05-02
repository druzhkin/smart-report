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


def test_research_policy_requires_paper_search_for_academic_question_without_papers():
    report = FinalReport(
        session_id="rp-academic",
        question="Compare peer-reviewed LLM observability benchmark papers",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer."),
        all_sources=[Source(title="Vendor blog", url="https://example.com/blog", tool="tavily")],
    )

    assessment = assess_research_policy(report.question, report)

    assert assessment.domain == "academic_research"
    assert assessment.recommended_services[0] == "paper_search"
    assert assessment.requires_academic_retrieval is True
    assert assessment.academic_retrieval_satisfied is False
    assert any("Academic retrieval is required" in issue for issue in assessment.issues)


def test_research_policy_accepts_paper_search_academic_sources():
    report = FinalReport(
        session_id="rp-academic-ok",
        question="Compare peer-reviewed LLM observability benchmark papers",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer."),
        all_sources=[
            Source(title="arXiv benchmark paper", url="https://arxiv.org/abs/2501.12345", tool="paper_search_mcp:arxiv"),
            Source(title="Semantic Scholar benchmark", url="https://www.semanticscholar.org/paper/abc", tool="paper_search_mcp:semantic"),
            Source(title="Papers with Code benchmark", url="https://paperswithcode.com/task/observability", tool="paper_search_mcp"),
            Source(title="Crossref paper", url="https://doi.org/10.1000/example", tool="paper_search_mcp:crossref"),
            Source(title="Academic benchmark dataset", url="https://arxiv.org/abs/2501.67890", tool="paper_search_mcp:arxiv"),
            Source(title="Official repository", url="https://github.com/example/benchmark", tool="exa"),
        ],
    )

    assessment = assess_research_policy(report.question, report)

    assert assessment.domain == "academic_research"
    assert assessment.academic_retrieval_satisfied is True
    assert assessment.tier1_count >= 2
    assert "academic" not in assessment.missing_source_families
    assert not any("Academic retrieval is required" in issue for issue in assessment.issues)


def test_research_policy_treats_english_moscow_real_estate_as_ru_domain():
    report = FinalReport(
        session_id="rp-en",
        question="Forecast Moscow primary real estate prices",
        executive_summary=ExecutiveSummaryV4(main_answer="Answer."),
        all_sources=[Source(title="Generic source", url="https://example.com")],
    )

    assessment = assess_research_policy(report.question, report)

    assert assessment.domain == "ru_real_estate"
    assert "cbr" in assessment.required_source_families
