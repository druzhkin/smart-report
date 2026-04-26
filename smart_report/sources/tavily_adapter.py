"""Tavily adapter implementing SearchBackend Protocol.

Wraps `TavilyClient` and re-shapes its `list[TavilyResult]` output to
the shared `SearchResult` shape from `smart_report.sources.base`.

Per v3 §0 invariant: `is_primary_capable = False` — Tavily is the
augment for `general` / `realtime_news` domains where Valyu's
proprietary corpora aren't a fit. Default `search_depth='basic'`
(cheap web), caller can pass 'advanced' for important queries.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .base import CostEstimate, Finding, SearchBackend, SearchResult, Source
from .tavily import TavilyClient, TavilyResult, TavilySearchError

_logger = logging.getLogger(__name__)


class TavilyAdapter:
    name = "tavily"
    is_primary_capable = False

    _COST_NOTE = "Tavily basic ~$0.005/call, advanced ~$0.020/call"
    _COST_PER_CALL_USD_BASIC = 0.005
    _COST_PER_CALL_USD_ADVANCED = 0.020

    def __init__(
        self,
        client: Optional[TavilyClient] = None,
        *,
        default_depth: str = "basic",
    ) -> None:
        if client is None:
            api_key = os.environ.get("TAVILY_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "TavilyAdapter requires TAVILY_API_KEY in env or an injected TavilyClient"
                )
            client = TavilyClient(api_key=api_key)
        self._client = client
        self._default_depth = default_depth

    async def search(
        self,
        query: str,
        *,
        domain_hint: Optional[str] = None,
        max_results: int = 10,
        cost_budget_usd: Optional[float] = None,
    ) -> SearchResult:
        # Pick depth based on domain hint: realtime_news + general → basic;
        # technical_research / regulatory_eu → advanced (callers may
        # explicitly want better coverage on harder questions).
        depth = self._default_depth
        if domain_hint in ("regulatory_eu", "regulatory_us", "technical_research"):
            depth = "advanced"

        t0 = time.monotonic()
        _logger.info(
            "tavily.search start", extra={
                "tavily_query": query[:120],
                "tavily_depth": depth,
                "tavily_domain_hint": domain_hint,
            },
        )
        try:
            raw = await self._client.search(
                query, search_depth=depth, max_results=max_results
            )
        except TavilySearchError as e:
            latency_ms = int((time.monotonic() - t0) * 1000)
            _logger.warning("tavily.search failed: %s", e)
            return SearchResult(
                findings=[], sources=[], raw_metadata={
                    "domain_hint": domain_hint, "depth": depth,
                },
                cost_usd=0.0,
                latency_ms=latency_ms,
                is_empty_or_error=True,
                error=f"TavilySearchError: {e}",
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        sources, findings = self._map_raw(raw)
        cost_usd = (
            self._COST_PER_CALL_USD_ADVANCED if depth == "advanced"
            else self._COST_PER_CALL_USD_BASIC
        )
        is_empty = not findings and not sources

        _logger.info(
            "tavily.search ok", extra={
                "tavily_result_count": len(raw),
                "tavily_cost_usd": cost_usd,
                "tavily_latency_ms": latency_ms,
            },
        )
        return SearchResult(
            findings=findings, sources=sources,
            raw_metadata={
                "domain_hint": domain_hint, "depth": depth,
                "raw_count": len(raw),
            },
            cost_usd=cost_usd, latency_ms=latency_ms,
            is_empty_or_error=is_empty,
        )

    @property
    def cost_per_call(self) -> CostEstimate:
        per_call = (
            self._COST_PER_CALL_USD_ADVANCED if self._default_depth == "advanced"
            else self._COST_PER_CALL_USD_BASIC
        )
        return CostEstimate(per_call_usd=per_call, notes=self._COST_NOTE)

    def _map_raw(self, raw: list[TavilyResult]) -> tuple[list[Source], list[Finding]]:
        if not raw:
            return ([], [])
        sources: list[Source] = []
        findings: list[Finding] = []
        by_url: dict[str, Source] = {}
        for tr in raw:
            url = tr.url or ""
            if not url:
                continue
            src = by_url.get(url)
            if src is None:
                src = Source(
                    url=url,
                    title=tr.title or None,
                    snippet=(tr.content or "")[:400] if tr.content else None,
                    backend=self.name,
                    raw_metadata={
                        "score": tr.score,
                        "published_date": tr.published_date,
                    },
                    quality_tier=None,  # Step 3.3 classifier owns this
                )
                by_url[url] = src
                sources.append(src)
            if tr.content:
                findings.append(
                    Finding(
                        text=tr.content, sources=[src],
                        raw_metadata={"score": tr.score},
                    )
                )
        return (sources, findings)
