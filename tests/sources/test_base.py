"""v3 brief §5.6 — SearchBackend Protocol shared dataclass invariants."""

from __future__ import annotations

from smart_report.sources.base import (
    CostEstimate,
    Finding,
    SearchBackend,
    SearchResult,
    Source,
)


def test_source_default_quality_tier_is_none():
    """Adapters must NOT pre-grade. Step 3.3 classifier owns quality_tier."""
    s = Source(url="https://example.com")
    assert s.quality_tier is None


def test_search_result_default_is_empty_or_error_is_false():
    """The flag is opt-in by adapter; default is "result is fine".

    Augment-on-failure routing in v3 §3.4 hinges on this flag, so the
    default must NOT trigger fallback by accident on a successful result.
    """
    sr = SearchResult(findings=[], sources=[], raw_metadata={})
    assert sr.is_empty_or_error is False
    assert sr.error is None


def test_search_result_carries_cost_and_latency():
    """Cost + latency flow through for budget and observability."""
    sr = SearchResult(
        findings=[],
        sources=[],
        raw_metadata={},
        cost_usd=0.012,
        latency_ms=4500,
    )
    assert sr.cost_usd == 0.012
    assert sr.latency_ms == 4500


def test_finding_holds_back_reference_to_sources():
    """Every Finding cites at least one Source — required for Step 3.3
    classifier to assign quality_tier propagation."""
    src = Source(url="https://example.com", backend="perplexity")
    f = Finding(text="The answer is 42", sources=[src])
    assert f.sources == [src]
    assert f.text == "The answer is 42"


def test_cost_estimate_dataclass():
    c = CostEstimate(per_call_usd=0.008, notes="sonar-pro")
    assert c.per_call_usd == 0.008
    assert "sonar-pro" in c.notes


def test_protocol_runtime_check_accepts_minimal_implementation():
    """The Protocol is runtime-checkable so the orchestrator can
    isinstance-check injected backends defensively."""

    class _Stub:
        name = "stub"
        is_primary_capable = False

        async def search(self, query, *, domain_hint=None, max_results=10, cost_budget_usd=None):
            return SearchResult(findings=[], sources=[], raw_metadata={})

        @property
        def cost_per_call(self) -> CostEstimate:
            return CostEstimate(per_call_usd=0.0)

    assert isinstance(_Stub(), SearchBackend)
