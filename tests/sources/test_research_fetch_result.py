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


# ---------------------------------------------------------------------------
# Exa
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exa_fetch_result_handles_dict_output_field():
    """Production bug: Exa's `output` field came back as a dict, not str.
    `len(markdown.split())` raised AttributeError. Coercion must unwrap."""
    client = _make_exa_client({
        "status": "completed",
        "output": {"content": "# Findings\n\nThis is the actual report markdown."},
        "citations": [{"url": "https://example.com", "title": "Example"}],
    })
    result = await client.fetch_result("r_test")
    assert isinstance(result.markdown, str)
    assert "Findings" in result.markdown
    assert result.word_count > 0
    assert result.sources_count == 1


@pytest.mark.asyncio
async def test_exa_fetch_result_handles_dict_output_with_markdown_key():
    client = _make_exa_client({
        "status": "completed",
        "output": {"markdown": "# Report\n\nBody text"},
        "citations": [],
    })
    result = await client.fetch_result("r_test")
    assert "Report" in result.markdown


@pytest.mark.asyncio
async def test_exa_fetch_result_handles_list_of_strings():
    client = _make_exa_client({
        "status": "completed",
        "output": ["Section A.\n\nA1 content.", "Section B.\n\nB1 content."],
        "citations": [],
    })
    result = await client.fetch_result("r_test")
    assert "Section A" in result.markdown
    assert "Section B" in result.markdown


@pytest.mark.asyncio
async def test_exa_fetch_result_handles_plain_string():
    """The original happy path — string field works as before."""
    client = _make_exa_client({
        "status": "completed",
        "report": "# Direct markdown report\n\nNo nesting.",
        "citations": [],
    })
    result = await client.fetch_result("r_test")
    assert "Direct markdown" in result.markdown


@pytest.mark.asyncio
async def test_exa_fetch_result_falls_back_to_json_dump_for_unknown_dict():
    """Dict without any recognised content key: dump as JSON code block."""
    client = _make_exa_client({
        "status": "completed",
        "output": {"weird_field": "x", "another": [1, 2]},
        "citations": [],
    })
    result = await client.fetch_result("r_test")
    assert "```json" in result.markdown
    assert "weird_field" in result.markdown


@pytest.mark.asyncio
async def test_exa_fetch_result_raises_when_truly_empty():
    client = _make_exa_client({
        "status": "completed",
        # No content fields at all
        "citations": [],
    })
    with pytest.raises(ExaResearchError):
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
async def test_tavily_fetch_result_handles_plain_string():
    client = _make_tavily_client({
        "status": "completed",
        "answer": "Plain string answer",
        "sources": [],
    })
    result = await client.fetch_result("req_test")
    assert result.markdown.startswith("Plain string answer")
