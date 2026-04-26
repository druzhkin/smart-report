"""Tests for the feature-flag pre-analyze augment (M1 D2 B2.1).

Per brief acceptance: 2 unit tests + 1 regression test (Q2 Moscow RE
NOT routing to Valyu when financial_us is enabled — proves selectivity).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from smart_report.models import UploadedMarkdown
from smart_report.sources.base import SearchResult, Source
from smart_report.sources.pre_analyze_augment import (
    ValyuPrimaryFailedError,
    maybe_run_valyu_augment,
)


def _mock_adapter_with_results(sources: list[Source]) -> MagicMock:
    adapter = MagicMock()
    adapter.search = AsyncMock(
        return_value=SearchResult(
            findings=[],
            sources=sources,
            raw_metadata={},
            cost_usd=0.04,
            latency_ms=4250,
            is_empty_or_error=False,
        )
    )
    return adapter


def _mock_adapter_empty() -> MagicMock:
    adapter = MagicMock()
    adapter.search = AsyncMock(
        return_value=SearchResult(
            findings=[],
            sources=[],
            raw_metadata={},
            cost_usd=0.0,
            latency_ms=120,
            is_empty_or_error=True,
            error=None,
        )
    )
    return adapter


# ---------------------------------------------------------------------------
# Unit 1: financial_us enabled + financial query → Valyu fires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_financial_us_enabled_fires_valyu_with_force_domain(monkeypatch):
    """With force_domain override, augment fires regardless of question text.
    This is how Q1 EV (which detects as ru_automotive heuristically) can
    still route to Valyu when the operator forces financial_us."""
    monkeypatch.setenv("SMART_REPORT_VALYU_ENABLE_DOMAINS", "financial_us")
    monkeypatch.setenv("SMART_REPORT_VALYU_FORCE_DOMAIN", "financial_us")

    adapter = _mock_adapter_with_results([
        Source(
            url="https://sec.gov/Archives/edgar/data/1318605/Tesla-10K-2024.htm",
            title="Tesla 10-K 2024",
            snippet="FY2024 revenue $97.7B",
            backend="valyu",
            raw_metadata={"valyu_source": "valyu/valyu-sec-filings", "publication_date": "2025-01-30"},
        ),
        Source(
            url="https://fred.stlouisfed.org/series/FEDFUNDS",
            title="Fed Funds Rate",
            snippet="Sep 2024 5.33%",
            backend="valyu",
            raw_metadata={"valyu_source": "valyu/valyu-fred"},
        ),
    ])

    upload, result, domain = await maybe_run_valyu_augment(
        "Russia electric vehicle market analysis", valyu_adapter=adapter
    )

    assert upload is not None
    assert isinstance(upload, UploadedMarkdown)
    assert "valyu_financial_us_augment.md" == upload.filename
    assert "sec.gov" in upload.content
    assert "fred.stlouisfed.org" in upload.content
    assert result is not None
    assert len(result.sources) == 2
    assert domain == "financial_us"
    adapter.search.assert_called_once()
    kwargs = adapter.search.call_args.kwargs
    assert kwargs["domain_hint"] == "financial_us"


# ---------------------------------------------------------------------------
# Unit 2: flag off → no augment, regardless of question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_skips_augment(monkeypatch):
    monkeypatch.delenv("SMART_REPORT_VALYU_ENABLE_DOMAINS", raising=False)
    adapter = _mock_adapter_with_results([])
    upload, result, domain = await maybe_run_valyu_augment(
        "Tesla SEC filings 2024", valyu_adapter=adapter
    )
    assert upload is None
    assert result is None
    adapter.search.assert_not_called()


# ---------------------------------------------------------------------------
# Regression: Q2 Moscow RE (russian_market) does NOT route when
# financial_us is the only enabled domain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_russian_market_query_not_routed_when_only_financial_us_enabled(monkeypatch):
    """Q2 Moscow RE is a Russian-RE query; even with financial_us enabled,
    it should NOT trigger Valyu (routing matrix says russian_market is
    Perplexity-primary and Day 5 capability map says Valyu doesn't cover
    Russian sources). No call to Valyu, no exception."""
    monkeypatch.setenv("SMART_REPORT_VALYU_ENABLE_DOMAINS", "financial_us")
    monkeypatch.delenv("SMART_REPORT_VALYU_FORCE_DOMAIN", raising=False)

    adapter = _mock_adapter_with_results([])
    upload, result, domain = await maybe_run_valyu_augment(
        "Какие тренды повлияют на девелоперов бизнес-сегмента жилья в Москве в 2026-2027?",
        valyu_adapter=adapter,
    )
    assert upload is None
    assert result is None
    assert domain == "russian_market"
    adapter.search.assert_not_called()


# ---------------------------------------------------------------------------
# Fail-fast: enabled domain + Valyu empty/error → raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enabled_domain_with_empty_valyu_raises(monkeypatch):
    """Per brief: ValyuPrimaryFailedError surfaces failure, doesn't silent-fall-back."""
    monkeypatch.setenv("SMART_REPORT_VALYU_ENABLE_DOMAINS", "financial_us")
    monkeypatch.setenv("SMART_REPORT_VALYU_FORCE_DOMAIN", "financial_us")
    adapter = _mock_adapter_empty()
    with pytest.raises(ValyuPrimaryFailedError, match="financial_us"):
        await maybe_run_valyu_augment("test", valyu_adapter=adapter)


@pytest.mark.asyncio
async def test_force_domain_overrides_question_classification(monkeypatch):
    """With force_domain set, question text classification ignored."""
    monkeypatch.setenv("SMART_REPORT_VALYU_ENABLE_DOMAINS", "scientific")
    monkeypatch.setenv("SMART_REPORT_VALYU_FORCE_DOMAIN", "scientific")
    adapter = _mock_adapter_with_results([
        Source(url="https://arxiv.org/abs/2024.12345", title="Paper", backend="valyu"),
    ])
    # Question is generic English, would heuristic-detect to "general", not scientific
    upload, result, domain = await maybe_run_valyu_augment(
        "what is going on with stuff", valyu_adapter=adapter
    )
    assert domain == "scientific"
    assert upload is not None
