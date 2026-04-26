"""TavilyAdapter tests — mock-only, mirrors test_valyu_adapter.py shape.

Live smoke is gated behind `@pytest.mark.live` and consumes the real
TAVILY_API_KEY (~$0.005/call basic).
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from smart_report.sources.base import SearchBackend, SearchResult
from smart_report.sources.tavily import TavilyClient, TavilyResult, TavilySearchError
from smart_report.sources.tavily_adapter import TavilyAdapter


def _make_mock_client(
    results: list[TavilyResult] | None = None,
    raises: Exception | None = None,
) -> MagicMock:
    client = MagicMock(spec=TavilyClient)
    if raises is not None:
        client.search = AsyncMock(side_effect=raises)
    else:
        client.search = AsyncMock(return_value=results or [])
    return client


@pytest.mark.asyncio
async def test_adapter_returns_searchresult_with_sources_and_findings():
    client = _make_mock_client(
        results=[
            TavilyResult(
                url="https://example.com/openai-news",
                title="OpenAI launches GPT-9",
                content="OpenAI announced GPT-9 today...",
                score=0.91,
                published_date="2026-04-26",
            ),
        ]
    )
    adapter = TavilyAdapter(client=client)
    result = await adapter.search("OpenAI GPT-9 launch", domain_hint="realtime_news")
    assert isinstance(result, SearchResult)
    assert len(result.sources) == 1
    assert len(result.findings) == 1
    assert result.sources[0].url == "https://example.com/openai-news"
    assert result.sources[0].backend == "tavily"
    assert result.sources[0].quality_tier is None
    assert not result.is_empty_or_error


@pytest.mark.asyncio
async def test_adapter_picks_advanced_depth_for_regulatory_hint():
    client = _make_mock_client(results=[])
    adapter = TavilyAdapter(client=client)
    await adapter.search("EU AI Act art 6", domain_hint="regulatory_eu")
    kwargs = client.search.call_args.kwargs
    assert kwargs["search_depth"] == "advanced"


@pytest.mark.asyncio
async def test_adapter_uses_basic_depth_by_default():
    client = _make_mock_client(results=[])
    adapter = TavilyAdapter(client=client)
    await adapter.search("today's weather", domain_hint="general")
    kwargs = client.search.call_args.kwargs
    assert kwargs["search_depth"] == "basic"


@pytest.mark.asyncio
async def test_adapter_dedupes_sources_when_same_url():
    client = _make_mock_client(
        results=[
            TavilyResult(url="https://x.com/a", title="A1", content="snippet A1"),
            TavilyResult(url="https://x.com/a", title="A2", content="snippet A2"),
        ]
    )
    adapter = TavilyAdapter(client=client)
    result = await adapter.search("dup query")
    assert len(result.sources) == 1
    assert len(result.findings) == 2


@pytest.mark.asyncio
async def test_adapter_empty_results_flag_set():
    client = _make_mock_client(results=[])
    adapter = TavilyAdapter(client=client)
    result = await adapter.search("very obscure query xyzzy")
    assert result.findings == []
    assert result.sources == []
    assert result.is_empty_or_error is True
    assert result.error is None


@pytest.mark.asyncio
async def test_adapter_error_surfaces_via_flag_not_raise():
    client = _make_mock_client(raises=TavilySearchError("retries exhausted"))
    adapter = TavilyAdapter(client=client)
    result = await adapter.search("test")
    assert result.is_empty_or_error is True
    assert result.error is not None
    assert "TavilySearchError" in result.error


@pytest.mark.asyncio
async def test_adapter_passes_protocol_isinstance_check():
    adapter = TavilyAdapter(client=_make_mock_client(results=[]))
    assert isinstance(adapter, SearchBackend)


def test_adapter_is_primary_capable_false_invariant():
    """v3 §0: Tavily is augment-only; Valyu remains the only primary-capable backend."""
    adapter = TavilyAdapter(client=_make_mock_client(results=[]))
    assert adapter.is_primary_capable is False


def test_adapter_cost_per_call_property():
    adapter = TavilyAdapter(client=_make_mock_client(results=[]))
    cost = adapter.cost_per_call
    assert cost.per_call_usd > 0
    assert cost.notes


@pytest.mark.live
@pytest.mark.asyncio
async def test_adapter_live_smoke_basic_query():
    """Real Tavily call (~$0.005). Run with: pytest -m live tests/sources/test_tavily_adapter.py"""
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")
    if not os.environ.get("TAVILY_API_KEY"):
        pytest.skip("TAVILY_API_KEY not set")
    adapter = TavilyAdapter()
    result = await adapter.search("OpenAI GPT-5 announcement 2024", max_results=5)
    assert not result.is_empty_or_error, f"tavily live failed: {result.error}"
    assert len(result.sources) >= 1
