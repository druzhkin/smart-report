"""Tests for v4.5 week-7 Day 2 — minimal Valyu client.

Mock-only by default. The live smoke test is gated on
``@pytest.mark.live`` and skipped in CI; run with
``pytest -m live`` after exporting VALYU_API_KEY.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from smart_report.sources.valyu import (
    _MAX_VALYU_ATTEMPTS,
    ValyuClient,
    ValyuResult,
    ValyuSearchError,
    _to_valyu_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_sdk_result(**overrides):
    """Build a MagicMock that mimics the SDK SearchResult shape."""
    defaults = {
        "url": "https://example.com/foo",
        "title": "Example title",
        "content": "Some content",
        "source": "valyu/valyu-fred",
        "price": 0.005,
        "relevance_score": 0.9,
        "publication_date": "2026-01-15",
        "data_type": "structured",
        "metadata": {"symbol": "GDP"},
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _fake_sdk_response(results, success=True, error=None):
    obj = MagicMock()
    obj.success = success
    obj.error = error
    obj.results = results
    return obj


def _fake_http_error(status: int) -> requests.HTTPError:
    response = MagicMock()
    response.status_code = status
    err = requests.HTTPError(response=response)
    return err


# ---------------------------------------------------------------------------
# Spec acceptance: mock success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_success_returns_mapped_results():
    sdk = MagicMock()
    sdk.search.return_value = _fake_sdk_response([
        _fake_sdk_result(url="https://fred.stlouisfed.org/series/GDP", title="US GDP"),
        _fake_sdk_result(url="https://bls.gov/data/cpi", title="US CPI"),
    ])
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    results = await client.search("US macro indicators 2026")
    assert len(results) == 2
    assert all(isinstance(r, ValyuResult) for r in results)
    assert results[0].url == "https://fred.stlouisfed.org/series/GDP"
    assert results[0].title == "US GDP"
    # Verify SDK was called with our defaults
    sdk.search.assert_called_once()
    kwargs = sdk.search.call_args.kwargs
    # fast_mode + search_type="proprietary" is rejected by the live API,
    # so default search_type is "all" — see BLOCKERS.md A3
    assert kwargs["search_type"] == "all"
    assert kwargs["fast_mode"] is True


@pytest.mark.asyncio
async def test_search_passes_through_optional_params():
    sdk = MagicMock()
    sdk.search.return_value = _fake_sdk_response([])
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    await client.search(
        "Tesla 10-K FY2024",
        search_type="proprietary",
        category="company",
        max_results=5,
        included_sources=["valyu/valyu-sec-filings"],
    )
    kwargs = sdk.search.call_args.kwargs
    assert kwargs["category"] == "company"
    assert kwargs["max_num_results"] == 5
    assert kwargs["included_sources"] == ["valyu/valyu-sec-filings"]


@pytest.mark.asyncio
async def test_search_empty_query_short_circuits():
    sdk = MagicMock()
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    assert await client.search("") == []
    assert await client.search("   ") == []
    sdk.search.assert_not_called()


@pytest.mark.asyncio
async def test_search_empty_results_returns_empty_list():
    """No matches → empty list (NOT an error). Caller falls back to
    secondary backend per the brief's hybrid routing rule.
    """
    sdk = MagicMock()
    sdk.search.return_value = _fake_sdk_response([])
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    assert await client.search("very obscure query") == []


@pytest.mark.asyncio
async def test_search_propagates_valyu_error_response():
    """If the SDK returns success=False, raise ValyuSearchError."""
    sdk = MagicMock()
    sdk.search.return_value = _fake_sdk_response(
        [], success=False, error="invalid query syntax"
    )
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    with pytest.raises(ValyuSearchError, match="invalid query syntax"):
        await client.search("anything")


# ---------------------------------------------------------------------------
# Retry shim — mirrors Step 3.1 OpenRouter policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_retries_on_5xx():
    """503 on attempt 1, success on attempt 2 → returns results."""
    sdk = MagicMock()
    err = _fake_http_error(503)
    sdk.search.side_effect = [err, _fake_sdk_response([_fake_sdk_result()])]
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    with patch("smart_report.sources.valyu.asyncio.sleep", new=AsyncMock()):
        results = await client.search("test query that is long enough")
    assert len(results) == 1
    assert sdk.search.call_count == 2


@pytest.mark.asyncio
async def test_search_retries_on_connection_error():
    """ConnectionError on attempts 1 + 2, success on 3."""
    sdk = MagicMock()
    sdk.search.side_effect = [
        requests.ConnectionError("network blip"),
        requests.ConnectionError("still down"),
        _fake_sdk_response([_fake_sdk_result()]),
    ]
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    with patch("smart_report.sources.valyu.asyncio.sleep", new=AsyncMock()):
        results = await client.search("test query")
    assert len(results) == 1
    assert sdk.search.call_count == 3


@pytest.mark.asyncio
async def test_search_does_not_retry_on_4xx():
    """401 / 403 / 429 → raise immediately, no retry."""
    sdk = MagicMock()
    err = _fake_http_error(401)
    sdk.search.side_effect = err
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    with patch("smart_report.sources.valyu.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(requests.HTTPError):
            await client.search("test query")
    assert sdk.search.call_count == 1


@pytest.mark.asyncio
async def test_search_does_not_retry_on_429():
    """Rate-limit must not be amplified by retries — raises immediately."""
    sdk = MagicMock()
    err = _fake_http_error(429)
    sdk.search.side_effect = err
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    with patch("smart_report.sources.valyu.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(requests.HTTPError):
            await client.search("test query")
    assert sdk.search.call_count == 1


@pytest.mark.asyncio
async def test_search_max_retries_exhausted_raises_valyu_error():
    """Three transient failures → raises ValyuSearchError wrapping the
    last underlying exception (not the raw requests error — caller
    deals with one error type from this module).
    """
    sdk = MagicMock()
    sdk.search.side_effect = [requests.ConnectionError("fail")] * _MAX_VALYU_ATTEMPTS
    client = ValyuClient(api_key="dummy", sdk_factory=lambda: sdk)
    with patch("smart_report.sources.valyu.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(ValyuSearchError, match="retries exhausted"):
            await client.search("test query")
    assert sdk.search.call_count == _MAX_VALYU_ATTEMPTS


# ---------------------------------------------------------------------------
# Adapter — _to_valyu_result
# ---------------------------------------------------------------------------


def test_to_valyu_result_stringifies_structured_content():
    """SDK can return content as list[dict] for structured datasets;
    our adapter stringifies so downstream text consumers don't choke."""
    sdk_result = _fake_sdk_result(content=[{"period": "Q4 2024", "revenue": 95_000_000}])
    out = _to_valyu_result(sdk_result)
    assert isinstance(out.content, str)
    assert "Q4 2024" in out.content


def test_to_valyu_result_handles_missing_optional_fields():
    """SDK SearchResult has many Optional fields. Adapter must not
    crash on missing ones."""
    bare = MagicMock()
    bare.url = "https://x/y"
    bare.title = "T"
    bare.content = "c"
    bare.source = "s"
    bare.price = 0.0
    # Don't set the optionals — getattr returns the auto-magic mock
    # Override for missing ones to None to simulate Pydantic Optional=None
    for f in ("relevance_score", "publication_date", "data_type", "metadata"):
        setattr(bare, f, None)
    out = _to_valyu_result(bare)
    assert out.url == "https://x/y"
    assert out.metadata == {}


# ---------------------------------------------------------------------------
# Live smoke (skipped in CI — run with `pytest -m live`)
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.asyncio
async def test_search_live_smoke_against_arxiv():
    """One real Valyu fast call against the cheapest dataset
    (valyu-arxiv at $1 CPM = $0.001/call). Skipped by default; run
    explicitly with ``pytest -m live tests/test_valyu_client.py``.
    """
    api_key = os.environ.get("VALYU_API_KEY")
    if not api_key:
        pytest.skip("VALYU_API_KEY not set")
    client = ValyuClient(api_key=api_key)
    # Use search_type="all" + fast_mode=True (live-API-compatible, ~$0.001).
    # For proprietary-only access the caller MUST pass fast_mode=False —
    # see BLOCKERS.md A3.
    results = await client.search(
        "transformer architecture attention",
        search_type="all",
        max_results=3,
        fast_mode=True,
    )
    assert isinstance(results, list)
    # arxiv should reliably return at least one hit on this query
    assert len(results) >= 1
    assert all(isinstance(r, ValyuResult) for r in results)
    assert all(r.url.startswith("http") for r in results)
