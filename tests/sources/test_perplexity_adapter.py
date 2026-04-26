"""v3 brief §5.6 — Perplexity adapter behaviour preservation tests.

Critical guard: the adapter MUST NOT change behaviour of the underlying
`smart_report.search.search()`. If a future change requires modifying
the original to make the adapter work, that's a Protocol design bug,
not a refactoring task — see brief §5.6 hard rule.
"""

from __future__ import annotations

import pytest

from smart_report.sources.base import SearchBackend, SearchResult, Source
from smart_report.sources.perplexity_adapter import PerplexityAdapter


# ---------------------------------------------------------------------------
# Mock search functions — match the smart_report.search.search() signature
# (returns list[dict] with claim/number/source_url/source_type/verbatim_quote)
# ---------------------------------------------------------------------------


async def _two_findings_two_sources(query: str) -> list[dict]:
    return [
        {
            "claim": "Russia EV market reached 1.2% share in Q1 2026",
            "number": "1.2%",
            "source_url": "https://zr.ru/article/ev-q1-2026",
            "source_type": "media",
            "verbatim_quote": "Доля электромобилей в России составила 1.2%",
        },
        {
            "claim": "Moskvich aims for 30% local content by end of 2026",
            "number": "30%",
            "source_url": "https://strategy.ru/moskvich-2026-roadmap",
            "source_type": "industry",
            "verbatim_quote": "К концу 2026 локализация Moskvich достигнет 30%",
        },
    ]


async def _two_findings_same_source(query: str) -> list[dict]:
    """Two claims citing the same URL → must produce 1 Source + 2 Findings."""
    return [
        {
            "claim": "EV charger count crossed 5000 in Russia 2025",
            "number": "5000",
            "source_url": "https://example.gov.ru/ev-infra-2025",
            "source_type": "official",
            "verbatim_quote": "more than 5000 charging stations",
        },
        {
            "claim": "Moscow-SPb corridor concentrates 60% of chargers",
            "number": "60%",
            "source_url": "https://example.gov.ru/ev-infra-2025",
            "source_type": "official",
            "verbatim_quote": "Москва-СПб коридор содержит 60%",
        },
    ]


async def _empty_results(query: str) -> list[dict]:
    return []


async def _raises(query: str) -> list[dict]:
    raise RuntimeError("Perplexity 503")


# ---------------------------------------------------------------------------
# Behaviour preservation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_returns_same_sources_as_underlying():
    adapter = PerplexityAdapter(search_fn=_two_findings_two_sources)
    result = await adapter.search("test query")
    urls = sorted(s.url for s in result.sources)
    assert urls == [
        "https://strategy.ru/moskvich-2026-roadmap",
        "https://zr.ru/article/ev-q1-2026",
    ]
    assert len(result.findings) == 2
    assert all(f.sources for f in result.findings)


@pytest.mark.asyncio
async def test_adapter_does_not_pre_grade_sources():
    """Step 3.3 classifier owns quality_tier. Adapter must leave it None."""
    adapter = PerplexityAdapter(search_fn=_two_findings_two_sources)
    result = await adapter.search("test query")
    for src in result.sources:
        assert src.quality_tier is None, (
            f"Source {src.url} arrived from adapter with pre-graded quality_tier "
            f"{src.quality_tier!r} — this breaks Phase 3.3 classifier ownership."
        )


@pytest.mark.asyncio
async def test_adapter_is_primary_capable_is_false():
    """v3 brief §0 invariant: only Valyu may be primary on covered domains.
    Perplexity is augment for Valyu-covered, primary for russian/news/general
    per routing matrix — but `is_primary_capable` is a per-backend capability
    flag, not a routing decision. Perplexity declares False; routing matrix
    handles when it's allowed to act as primary."""
    adapter = PerplexityAdapter(search_fn=_two_findings_two_sources)
    assert adapter.is_primary_capable is False


@pytest.mark.asyncio
async def test_adapter_dedupes_sources_when_same_url():
    """Multiple findings citing one URL → 1 Source + 2 Findings (each pointing
    to the shared Source)."""
    adapter = PerplexityAdapter(search_fn=_two_findings_same_source)
    result = await adapter.search("test query")
    assert len(result.sources) == 1
    assert len(result.findings) == 2
    # Both findings point to the same Source instance (identity, not equality)
    assert result.findings[0].sources[0] is result.sources[0]
    assert result.findings[1].sources[0] is result.sources[0]


@pytest.mark.asyncio
async def test_adapter_empty_results_flag_is_set():
    """Empty result → caller routes to fallback per v3 §3.4."""
    adapter = PerplexityAdapter(search_fn=_empty_results)
    result = await adapter.search("very obscure query")
    assert result.findings == []
    assert result.sources == []
    assert result.is_empty_or_error is True
    assert result.error is None  # empty isn't error


@pytest.mark.asyncio
async def test_adapter_exception_surfaces_as_error_flag_not_raise():
    """Adapter MUST NOT propagate the exception — orchestrator handles
    augment-on-failure routing via the error flag."""
    adapter = PerplexityAdapter(search_fn=_raises)
    result = await adapter.search("test query")
    assert result.is_empty_or_error is True
    assert result.error is not None
    assert "RuntimeError" in result.error
    assert "Perplexity 503" in result.error


@pytest.mark.asyncio
async def test_adapter_passes_protocol_isinstance_check():
    """The Protocol is runtime-checkable; adapter must satisfy it."""
    adapter = PerplexityAdapter(search_fn=_two_findings_two_sources)
    assert isinstance(adapter, SearchBackend)


@pytest.mark.asyncio
async def test_adapter_carries_cost_and_latency():
    adapter = PerplexityAdapter(search_fn=_two_findings_two_sources)
    result = await adapter.search("test query")
    assert result.cost_usd > 0
    # latency_ms should be small but non-negative for a sync mock
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_adapter_cost_per_call_property():
    adapter = PerplexityAdapter()
    cost = adapter.cost_per_call
    assert cost.per_call_usd > 0
    assert cost.notes  # non-empty
