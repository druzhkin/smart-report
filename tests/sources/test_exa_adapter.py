"""ExaAdapter tests — mock-only, mirrors test_valyu_adapter.py shape."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from smart_report.sources.base import SearchBackend, SearchResult
from smart_report.sources.exa import ExaClient, ExaResult, ExaSearchError
from smart_report.sources.exa_adapter import ExaAdapter


def _make_mock_client(
    results: list[ExaResult] | None = None,
    raises: Exception | None = None,
) -> MagicMock:
    client = MagicMock(spec=ExaClient)
    if raises is not None:
        client.search = AsyncMock(side_effect=raises)
    else:
        client.search = AsyncMock(return_value=results or [])
    return client


@pytest.mark.asyncio
async def test_adapter_returns_searchresult_with_sources_and_findings():
    client = _make_mock_client(
        results=[
            ExaResult(
                url="https://arxiv.org/abs/2401.0001",
                title="Scaling Laws for Mixture Models",
                text="We study scaling laws for sparse mixture-of-experts...",
                highlights=["MoE scaling exponent measured at 0.31"],
                score=0.88,
                published_date="2024-01-15",
                author="Smith et al.",
            ),
        ]
    )
    adapter = ExaAdapter(client=client)
    result = await adapter.search("MoE scaling laws", domain_hint="technical_research")
    assert isinstance(result, SearchResult)
    assert len(result.sources) == 1
    assert len(result.findings) == 1
    assert result.sources[0].url == "https://arxiv.org/abs/2401.0001"
    assert result.sources[0].backend == "exa"
    assert result.sources[0].quality_tier is None
    assert "MoE scaling" in (result.sources[0].snippet or "")
    assert not result.is_empty_or_error


@pytest.mark.asyncio
async def test_adapter_calls_exa_with_auto_type_default():
    client = _make_mock_client(results=[])
    adapter = ExaAdapter(client=client)
    await adapter.search("test")
    kwargs = client.search.call_args.kwargs
    assert kwargs["type"] == "auto"


@pytest.mark.asyncio
async def test_adapter_dedupes_sources_when_same_url():
    client = _make_mock_client(
        results=[
            ExaResult(url="https://arxiv.org/abs/2401.0001", title="A", text="snippet A"),
            ExaResult(url="https://arxiv.org/abs/2401.0001", title="A2", text="snippet B"),
        ]
    )
    adapter = ExaAdapter(client=client)
    result = await adapter.search("dup")
    assert len(result.sources) == 1
    assert len(result.findings) == 2


@pytest.mark.asyncio
async def test_adapter_empty_results_flag_set():
    client = _make_mock_client(results=[])
    adapter = ExaAdapter(client=client)
    result = await adapter.search("very obscure query xyzzy")
    assert result.findings == []
    assert result.sources == []
    assert result.is_empty_or_error is True
    assert result.error is None


@pytest.mark.asyncio
async def test_adapter_error_surfaces_via_flag_not_raise():
    client = _make_mock_client(raises=ExaSearchError("retries exhausted"))
    adapter = ExaAdapter(client=client)
    result = await adapter.search("test")
    assert result.is_empty_or_error is True
    assert result.error is not None
    assert "ExaSearchError" in result.error


@pytest.mark.asyncio
async def test_adapter_passes_protocol_isinstance_check():
    adapter = ExaAdapter(client=_make_mock_client(results=[]))
    assert isinstance(adapter, SearchBackend)


def test_adapter_is_primary_capable_false_invariant():
    adapter = ExaAdapter(client=_make_mock_client(results=[]))
    assert adapter.is_primary_capable is False


def test_adapter_cost_per_call_property():
    adapter = ExaAdapter(client=_make_mock_client(results=[]))
    cost = adapter.cost_per_call
    assert cost.per_call_usd > 0
    assert cost.notes


@pytest.mark.live
@pytest.mark.asyncio
async def test_adapter_live_smoke_arxiv_search():
    """Real Exa call (~$0.005-0.020). Run with: pytest -m live tests/sources/test_exa_adapter.py"""
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")
    if not os.environ.get("EXA_API_KEY"):
        pytest.skip("EXA_API_KEY not set")
    adapter = ExaAdapter()
    result = await adapter.search(
        "transformer attention mechanism", domain_hint="technical_research", max_results=5,
    )
    assert not result.is_empty_or_error, f"exa live failed: {result.error}"
    assert len(result.sources) >= 1
