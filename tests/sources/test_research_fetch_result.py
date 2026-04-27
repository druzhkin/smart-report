"""Regression tests for ExaResearchClient + TavilyResearchClient fetch_result.

Bug 2026-04-27 (prod 500 every poll): Exa returned a dict in `output`
field where we expected a string, so `markdown.split()` raised
AttributeError. The fix is defensive coercion (`_coerce_to_md`) — these
tests pin that behavior across both clients.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from smart_report.sources.exa_research import ExaResearchClient, ExaResearchError
from smart_report.sources.tavily_research import TavilyResearchClient


def _make_exa_client(status_response: dict) -> ExaResearchClient:
    """Construct an ExaResearchClient whose SDK returns the given dict from .research.get()."""
    sdk = MagicMock()
    sdk.research.get = MagicMock(return_value=status_response)
    return ExaResearchClient(api_key="test", sdk_factory=lambda: sdk)


def _make_tavily_client(status_response: dict) -> TavilyResearchClient:
    sdk = MagicMock()
    sdk.get_research = MagicMock(return_value=status_response)
    return TavilyResearchClient(api_key="test", sdk_factory=lambda: sdk)


def _make_valyu_client(status_response: dict):
    """Construct a ValyuResearchClient whose SDK returns this from .deepresearch.status()."""
    from smart_report.sources.valyu_deepresearch import ValyuResearchClient
    sdk = MagicMock()
    sdk.deepresearch.status = MagicMock(return_value=status_response)
    return ValyuResearchClient(api_key="test", sdk_factory=lambda: sdk)


# ---------------------------------------------------------------------------
# Exa
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exa_fetch_result_reads_output_content():
    """Per Exa SDK ResearchCompletedDto: report markdown is in output.content."""
    client = _make_exa_client({
        "status": "completed",
        "output": {"content": "# Findings\n\nReport body.", "parsed": None},
        "events": [],
    })
    result = await client.fetch_result("r_test")
    assert "Findings" in result.markdown
    assert result.word_count > 0


@pytest.mark.asyncio
async def test_exa_fetch_result_extracts_urls_from_events():
    """Citations come from events[] — search/crawl operations carry URLs."""
    client = _make_exa_client({
        "status": "completed",
        "output": {"content": "# Body", "parsed": None},
        "events": [
            {
                "event_type": "task-operation",
                "data": {
                    "type": "search",
                    "search_type": "auto",
                    "query": "test",
                    "results": [
                        {"url": "https://example.com/a"},
                        {"url": "https://example.com/b"},
                    ],
                },
            },
            {
                "event_type": "task-operation",
                "data": {
                    "type": "crawl",
                    "result": {"url": "https://example.com/c"},
                },
            },
            # Duplicate URL — must be deduped
            {
                "event_type": "task-operation",
                "data": {
                    "type": "search",
                    "results": [{"url": "https://example.com/a"}],
                },
            },
            # think operation has no urls
            {"event_type": "task-operation", "data": {"type": "think", "content": "thinking"}},
        ],
    })
    result = await client.fetch_result("r_test")
    assert result.sources_count == 3  # a, b, c — deduped
    # Sources section appended to markdown
    assert "## Sources" in result.markdown
    assert "https://example.com/a" in result.markdown
    assert "https://example.com/c" in result.markdown


@pytest.mark.asyncio
async def test_exa_fetch_result_handles_parsed_schema_output():
    """When output_schema was used, content is empty, parsed has the JSON."""
    client = _make_exa_client({
        "status": "completed",
        "output": {"content": "", "parsed": {"answer": "42", "confidence": 0.9}},
        "events": [],
    })
    result = await client.fetch_result("r_test")
    assert "```json" in result.markdown
    assert "answer" in result.markdown


@pytest.mark.asyncio
async def test_exa_fetch_result_falls_back_to_url_scrape_when_no_events():
    """If events absent (some SDK versions), scrape URLs from the body."""
    client = _make_exa_client({
        "status": "completed",
        "output": {
            "content": "Per https://example.com/x and https://example.com/y, the answer is X.",
            "parsed": None,
        },
        # No events
    })
    result = await client.fetch_result("r_test")
    assert result.sources_count == 2


@pytest.mark.asyncio
async def test_exa_fetch_result_raises_when_no_content():
    client = _make_exa_client({
        "status": "completed",
        "output": {"content": "", "parsed": None},
    })
    with pytest.raises(ExaResearchError, match="no output.content"):
        await client.fetch_result("r_test")


# ---------------------------------------------------------------------------
# Tavily — same defensive shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tavily_fetch_result_handles_dict_output_field():
    client = _make_tavily_client({
        "status": "completed",
        "output": {"content": "# Tavily report content"},
        "sources": [{"url": "https://x.com", "title": "X"}],
    })
    result = await client.fetch_result("req_test")
    assert "Tavily report" in result.markdown
    assert result.sources_count == 1


@pytest.mark.asyncio
async def test_valyu_fetch_result_reads_output_field():
    """Bug 2026-04-27: was calling get_assets(task_id) which requires
    asset_id positional arg. Markdown is in `output` field of status()."""
    from smart_report.sources.valyu_deepresearch import ValyuResearchClient
    client = _make_valyu_client({
        "status": "completed",
        "output": "# Real Valyu DR result\n\n4858 words of analysis...",
        "output_type": "markdown",
        "sources": [{"url": f"https://example.com/{i}"} for i in range(19)],
        "cost": 0.10,
    })
    result = await client.fetch_result("a1159e3d-test")
    assert "Real Valyu DR" in result.markdown
    assert result.sources_count == 19
    assert result.word_count > 0


@pytest.mark.asyncio
async def test_valyu_fetch_result_raises_when_output_missing():
    from smart_report.sources.valyu_deepresearch import (
        ValyuResearchClient, ValyuResearchError,
    )
    client = _make_valyu_client({
        "status": "completed",
        "output": "",
        "sources": [],
    })
    with pytest.raises(ValyuResearchError, match="no `output` markdown"):
        await client.fetch_result("test-id")


@pytest.mark.asyncio
async def test_tavily_fetch_result_handles_plain_string():
    client = _make_tavily_client({
        "status": "completed",
        "answer": "Plain string answer",
        "sources": [],
    })
    result = await client.fetch_result("req_test")
    assert result.markdown.startswith("Plain string answer")
