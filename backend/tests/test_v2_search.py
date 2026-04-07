from __future__ import annotations

from backend.v2.models import QuestionKind, ResearchPlan, ResearchQuestion, SearchCandidate, SourceType
from backend.v2.search import (
    _clean_extracted_text,
    _extract_preferred_html_region,
    _strip_html_tags,
    classify_source_type,
    normalize_source_url,
    select_sources,
)


def test_normalize_source_url_extracts_duckduckgo_redirect_target() -> None:
    url = (
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fhabr.com%2Fru%2Farticles%2F917316%2F"
        "&rut=9bd5b3884b27070d4e74882bd3d1c7236a739cbecbcdf595823403b156c65bbb"
    )

    assert normalize_source_url(url) == "https://habr.com/ru/articles/917316/"


def test_normalize_source_url_rejects_non_http_targets() -> None:
    assert normalize_source_url("javascript:alert(1)") is None


def test_github_html_extraction_prefers_readme_like_content() -> None:
    html_doc = """
    <html>
      <body>
        <header>Skip to content Sign in Activity stars 78 watchers 12</header>
        <article class="markdown-body entry-content container-lg">
          <h1>GPT Researcher</h1>
          <p>GPT Researcher is an open-source deep research agent for web, local files, and MCP-connected tools.</p>
          <p>It supports section planning, source gathering, and long-form report generation for production workflows.</p>
        </article>
        <footer>Privacy Terms GitHub, Inc. Footer</footer>
      </body>
    </html>
    """

    region = _extract_preferred_html_region("https://github.com/assafelovic/gpt-researcher", html_doc)
    text = _clean_extracted_text(_strip_html_tags(region))

    assert "GPT Researcher is an open-source deep research agent" in text
    assert "section planning" in text
    assert "sign in" not in text.lower()
    assert "watchers" not in text.lower()


def test_classify_source_type_downgrades_github_topics_and_awesome_lists() -> None:
    assert classify_source_type("https://github.com/topics/llm-benchmarking") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://github.com/machinelearningzuu/awesome-llm-projects") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://github.com/assafelovic/gpt-researcher") == SourceType.OFFICIAL_DOCUMENTATION


def test_classify_source_type_downgrades_market_report_sellers_and_listicles() -> None:
    assert classify_source_type("https://www.marketgrowthreports.com/market-reports/enterprise-architecture-tools-market-111597") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://www.thecmo.com/tools/best-marketing-intelligence-software/") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://uxdesign.cc/exploring-product-architecture-a-case-study-a8d247f79960") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://thesignal.substack.com/p/the-best-llms-for-each-task-and-what") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://dev.to/synergy_shock/the-silent-evolution-of-llms-in-2026-2mc4") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://leetcode.com/discuss/post/7781082/example/") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://htdocs.dev/posts/the-10-best-open-source-projects-for-workflow-orchestration-and-automation/") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://www.bentoml.com/blog/navigating-the-world-of-open-source-large-language-models") == SourceType.HIGH_QUALITY_SECONDARY
    assert classify_source_type("https://www.pluralsight.com/resources/blog/ai-and-data/best-ai-models-2026-list") == SourceType.WEAK_SECONDARY
    assert classify_source_type("https://community.openai.com/t/foundational-must-read-gpt-llm-papers/197003") == SourceType.HIGH_QUALITY_SECONDARY
    assert classify_source_type("https://www.mordorintelligence.com/industry-reports/enterprise-architecture-tools-market") == SourceType.HIGH_QUALITY_SECONDARY
    assert classify_source_type("https://www.cambridge.org/core/journals/design-science/article/example") == SourceType.RESEARCH_PAPER


def test_select_sources_filters_low_signal_curated_pages() -> None:
    plan = ResearchPlan(
        primary_questions=[ResearchQuestion(question_id="q1", question="Which GitHub projects are production-ready?", kind=QuestionKind.PRIMARY)],
        required_source_mix=[
            SourceType.OFFICIAL_DOCUMENTATION,
            SourceType.BENCHMARK,
            SourceType.VENDOR_PAGE,
            SourceType.HIGH_QUALITY_SECONDARY,
        ],
    )
    candidates = [
        SearchCandidate(
            question_id="q1",
            query="github projects deep research",
            url="https://github.com/topics/llm-benchmarking",
            title="llm-benchmarking · GitHub Topics",
            domain="github.com",
            provider="duckduckgo",
        ),
        SearchCandidate(
            question_id="q1",
            query="github projects deep research",
            url="https://github.com/machinelearningzuu/awesome-llm-projects",
            title="Awesome LLM Projects",
            domain="github.com",
            provider="duckduckgo",
        ),
        SearchCandidate(
            question_id="q1",
            query="github projects deep research",
            url="https://github.com/assafelovic/gpt-researcher",
            title="GitHub - assafelovic/gpt-researcher",
            domain="github.com",
            provider="duckduckgo",
        ),
    ]

    selected = select_sources(candidates, plan)

    assert [item.url for item in selected] == ["https://github.com/assafelovic/gpt-researcher"]
