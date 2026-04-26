"""Perplexity adapter implementing SearchBackend Protocol (v3 brief §5.6).

Wraps the existing `smart_report.search.search()` function (v3-era,
returns list[dict]) and maps its output to the shared `SearchResult`
shape. **Zero behaviour change** in the underlying Perplexity wrapper —
adapter only re-shapes the response.

Per v3 §0 invariant: `is_primary_capable = False`. Perplexity is an
augment for Valyu-covered domains and primary for `russian_market` /
`realtime_news` / `general` per the routing matrix.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from .base import CostEstimate, Finding, SearchBackend, SearchResult, Source


class PerplexityAdapter:
    """Adapter making `smart_report.search.search()` look like a SearchBackend.

    The constructor takes a search-callable so tests can inject a mock
    without monkey-patching the underlying module. Default uses the
    real `smart_report.search.search`.
    """

    name = "perplexity"
    is_primary_capable = False

    # Sonar-pro typical per-call cost. Perplexity bills per-API-call,
    # not per-token like OpenRouter. Source: pricing page 2025-Q3.
    _COST_NOTE = "Perplexity sonar-pro ~$0.005-0.010/call depending on result depth"
    _COST_PER_CALL_USD = 0.008

    def __init__(self, search_fn: Optional[Callable] = None) -> None:
        self._search_fn = search_fn

    async def search(
        self,
        query: str,
        *,
        domain_hint: Optional[str] = None,
        max_results: int = 10,
        cost_budget_usd: Optional[float] = None,
    ) -> SearchResult:
        # Lazy import lets tests pass an injected fn without importing
        # the real module (which pulls in httpx + Perplexity creds).
        if self._search_fn is None:
            from smart_report.search import search as _search

            self._search_fn = _search

        t0 = time.monotonic()
        try:
            raw = await self._search_fn(query)
        except Exception as e:
            return SearchResult(
                findings=[],
                sources=[],
                raw_metadata={"domain_hint": domain_hint, "max_results": max_results},
                cost_usd=self._COST_PER_CALL_USD,  # billed even on error
                latency_ms=int((time.monotonic() - t0) * 1000),
                is_empty_or_error=True,
                error=f"{type(e).__name__}: {e}",
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        sources, findings = self._map_raw(raw)
        is_empty = not findings and not sources
        return SearchResult(
            findings=findings,
            sources=sources,
            raw_metadata={
                "domain_hint": domain_hint,
                "max_results": max_results,
                "raw_count": len(raw) if isinstance(raw, list) else 0,
            },
            cost_usd=self._COST_PER_CALL_USD,
            latency_ms=latency_ms,
            is_empty_or_error=is_empty,
            error=None,
        )

    @property
    def cost_per_call(self) -> CostEstimate:
        return CostEstimate(
            per_call_usd=self._COST_PER_CALL_USD,
            notes=self._COST_NOTE,
        )

    def _map_raw(self, raw: Any) -> tuple[list[Source], list[Finding]]:
        """Map the raw `list[dict]` from `smart_report.search.search()` to
        Source + Finding lists. The dict shape is:
            {"claim": str, "number": str|None, "source_url": str,
             "source_type": str, "verbatim_quote": str|None}
        """
        if not isinstance(raw, list):
            return ([], [])

        sources: list[Source] = []
        findings: list[Finding] = []
        # Track (url -> Source) so multiple findings citing the same URL
        # share one Source instance; downstream classifier shouldn't see
        # duplicates.
        by_url: dict[str, Source] = {}

        for item in raw:
            if not isinstance(item, dict):
                continue
            url = item.get("source_url") or ""
            if not url:
                continue
            src = by_url.get(url)
            if src is None:
                src = Source(
                    url=url,
                    title=None,  # Perplexity raw doesn't include titles
                    snippet=item.get("verbatim_quote"),
                    backend=self.name,
                    raw_metadata={
                        "source_type": item.get("source_type"),
                        "number": item.get("number"),
                    },
                    # Quality tier is left None — Phase 3.3 classifier
                    # owns it. Adapters never pre-grade sources.
                    quality_tier=None,
                )
                by_url[url] = src
                sources.append(src)
            claim_text = item.get("claim") or ""
            if not claim_text:
                continue
            findings.append(
                Finding(
                    text=claim_text,
                    sources=[src],
                    raw_metadata={
                        "number": item.get("number"),
                        "source_type": item.get("source_type"),
                        "verbatim_quote": item.get("verbatim_quote"),
                    },
                )
            )

        return (sources, findings)
