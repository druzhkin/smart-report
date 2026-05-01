"""ValyuAdapter tests — M1 D1 B1.2 of two-week brief.

Mock-only by default. The live smoke (`@pytest.mark.live`) is the
acceptance criterion for B1.2 §3.7 minimum: real Valyu call on
`Tesla 10-K filing 2024` expecting >=3 sec.gov sources.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from smart_report.sources.base import SearchBackend, SearchResult
from smart_report.sources.valyu import ValyuClient, ValyuResult, ValyuSearchError
from smart_report.sources.valyu_adapter import ValyuAdapter

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_client(results: list[ValyuResult] | None = None,
                     raises: Exception | None = None) -> MagicMock:
    client = MagicMock(spec=ValyuClient)
    if raises is not None:
        client.search = AsyncMock(side_effect=raises)
    else:
        client.search = AsyncMock(return_value=results or [])
    return client


# ---------------------------------------------------------------------------
# Acceptance: success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_returns_searchresult_with_sources_and_findings():
    client = _make_mock_client(
        results=[
            ValyuResult(
                url="https://sec.gov/cgi-bin/browse-edgar?TSLA-10K-2024",
                title="Tesla 10-K 2024",
                content="Tesla reported FY2024 revenue of $97.7B...",
                source="valyu/valyu-sec-filings",
                price=0.005,
                relevance_score=0.92,
                publication_date="2025-01-30",
                data_type="structured",
                metadata={"cik": "0001318605"},
            ),
        ]
    )
    adapter = ValyuAdapter(valyu_client=client)
    result = await adapter.search("Tesla 10-K filing 2024", domain_hint="financial_us")

    assert isinstance(result, SearchResult)
    assert len(result.sources) == 1
    assert len(result.findings) == 1
    assert result.sources[0].url == "https://sec.gov/cgi-bin/browse-edgar?TSLA-10K-2024"
    assert result.sources[0].backend == "valyu"
    # Step 3.3 classifier owns quality_tier — adapter must NOT pre-grade
    assert result.sources[0].quality_tier is None
    # Valyu source dataset id passed through for downstream consumers
    assert result.sources[0].raw_metadata.get("valyu_source") == "valyu/valyu-sec-filings"
    assert not result.is_empty_or_error
    assert result.error is None


@pytest.mark.asyncio
async def test_adapter_passes_domain_hint_in_raw_metadata():
    client = _make_mock_client(results=[])
    adapter = ValyuAdapter(valyu_client=client)
    result = await adapter.search("foo", domain_hint="medical_clinical", max_results=8)
    assert result.raw_metadata["domain_hint"] == "medical_clinical"
    assert result.raw_metadata["max_results"] == 8


@pytest.mark.asyncio
async def test_adapter_calls_valyu_fast_all_for_non_scientific_domain():
    client = _make_mock_client(results=[])
    adapter = ValyuAdapter(valyu_client=client)
    await adapter.search("test", domain_hint="financial_us")
    kwargs = client.search.call_args.kwargs
    assert kwargs["fast_mode"] is True
    assert kwargs["search_type"] == "all"
    assert kwargs["included_sources"] is None


@pytest.mark.asyncio
async def test_adapter_forces_arxiv_for_technical_research_domain():
    client = _make_mock_client(results=[])
    adapter = ValyuAdapter(valyu_client=client)
    result = await adapter.search(
        "transformer attention mechanism",
        domain_hint="technical_research",
    )

    kwargs = client.search.call_args.kwargs
    assert kwargs["fast_mode"] is False
    assert kwargs["search_type"] == "proprietary"
    assert kwargs["included_sources"] == ["valyu/valyu-arxiv"]
    assert result.raw_metadata["included_sources"] == ["valyu/valyu-arxiv"]


@pytest.mark.asyncio
async def test_adapter_forces_paper_sources_for_scientific_and_medical_domains():
    client = _make_mock_client(results=[])
    adapter = ValyuAdapter(valyu_client=client)

    await adapter.search("direct air capture economics papers", domain_hint="scientific")
    scientific_kwargs = client.search.call_args.kwargs
    assert scientific_kwargs["search_type"] == "proprietary"
    assert scientific_kwargs["fast_mode"] is False
    assert scientific_kwargs["included_sources"] == [
        "valyu/valyu-arxiv",
        "valyu/valyu-pubmed",
        "valyu/valyu-biorxiv",
        "valyu/valyu-medrxiv",
    ]

    await adapter.search("phase 3 oncology trial", domain_hint="medical_clinical")
    medical_kwargs = client.search.call_args.kwargs
    assert medical_kwargs["search_type"] == "proprietary"
    assert medical_kwargs["fast_mode"] is False
    assert medical_kwargs["included_sources"] == [
        "valyu/valyu-pubmed",
        "valyu/valyu-medrxiv",
        "valyu/valyu-clinical-trials",
    ]


@pytest.mark.asyncio
async def test_adapter_dedupes_sources_when_same_url():
    client = _make_mock_client(
        results=[
            ValyuResult(
                url="https://fred.stlouisfed.org/series/CPILFESL",
                title="CPI",
                content="CPI rose 3.1% YoY in Sep 2024",
                source="valyu/valyu-fred",
                price=0.003,
            ),
            ValyuResult(
                url="https://fred.stlouisfed.org/series/CPILFESL",
                title="CPI (alt extract)",
                content="Core CPI Sep 2024: index value 318.7",
                source="valyu/valyu-fred",
                price=0.003,
            ),
        ]
    )
    adapter = ValyuAdapter(valyu_client=client)
    result = await adapter.search("US CPI Sep 2024")
    assert len(result.sources) == 1
    assert len(result.findings) == 2
    assert result.findings[0].sources[0] is result.sources[0]
    assert result.findings[1].sources[0] is result.sources[0]


# ---------------------------------------------------------------------------
# Empty + error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_empty_results_flag_set():
    client = _make_mock_client(results=[])
    adapter = ValyuAdapter(valyu_client=client)
    result = await adapter.search("very obscure query")
    assert result.findings == []
    assert result.sources == []
    assert result.is_empty_or_error is True
    assert result.error is None  # empty isn't error


@pytest.mark.asyncio
async def test_adapter_error_surfaces_via_flag_not_raise():
    """Per v3 §3.4 augment-on-failure: orchestrator routes via flag, NOT exception."""
    client = _make_mock_client(raises=ValyuSearchError("retries exhausted: ConnectionError"))
    adapter = ValyuAdapter(valyu_client=client)
    result = await adapter.search("test")
    assert result.is_empty_or_error is True
    assert result.error is not None
    assert "ValyuSearchError" in result.error


# ---------------------------------------------------------------------------
# Protocol contract + invariant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_passes_protocol_isinstance_check():
    adapter = ValyuAdapter(valyu_client=_make_mock_client(results=[]))
    assert isinstance(adapter, SearchBackend)


def test_adapter_is_primary_capable_true():
    """v3 §0 invariant: Valyu is the ONLY backend with is_primary_capable=True."""
    adapter = ValyuAdapter(valyu_client=_make_mock_client(results=[]))
    assert adapter.is_primary_capable is True


def test_adapter_cost_per_call_property():
    adapter = ValyuAdapter(valyu_client=_make_mock_client(results=[]))
    cost = adapter.cost_per_call
    assert cost.per_call_usd > 0
    assert cost.notes


# ---------------------------------------------------------------------------
# Live smoke (B1.2 acceptance per brief §3.7)
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.asyncio
async def test_adapter_live_smoke_tesla_10k():
    """Real Valyu call on Tesla 10-K. Per brief: >=3 sources with sec.gov.

    Cost: ~$0.05-0.10 (fast tier, 10 results × $0.005-0.010 each).
    Run with: pytest -m live tests/sources/test_valyu_adapter.py
    """
    # Load .env explicitly (pytest doesn't pick up dotenv automatically)
    from pathlib import Path

    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")
    if not os.environ.get("VALYU_API_KEY"):
        pytest.skip("VALYU_API_KEY not set")
    adapter = ValyuAdapter()
    result = await adapter.search(
        "Tesla 10-K filing 2024 revenue",
        domain_hint="financial_us",
        max_results=10,
    )
    assert isinstance(result, SearchResult)
    assert not result.is_empty_or_error, f"valyu live failed: {result.error}"
    sec_sources = [s for s in result.sources if "sec.gov" in s.url.lower()]
    assert len(sec_sources) >= 3, (
        f"Expected >=3 sec.gov sources, got {len(sec_sources)} "
        f"of {len(result.sources)} total. URLs: "
        f"{[s.url[:80] for s in result.sources[:10]]}"
    )
