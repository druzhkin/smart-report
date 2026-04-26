"""Valyu adapter implementing SearchBackend Protocol (M1 D1 B1.2 of two-week brief).

Wraps the existing `ValyuClient` (Day 2 work) and re-shapes its `list[ValyuResult]`
output to the shared `SearchResult` shape from `smart_report.sources.base`.

Per v3 §0 architectural invariant + `tests/test_routing_invariants.py`:
`is_primary_capable = True` — Valyu is the ONLY backend allowed to be primary
on covered domains.

Per two-week brief §3 B1.2 v0: `fast_mode=True` hardcoded for this minimum
viable production version. M2 may refine per-domain `included_sources` filters
once the financial_us live smoke validates the basic path. Day 5 capability
map enumerated 36 datasets — financial_us specifically benefits from
`valyu/valyu-sec-filings`, `valyu/valyu-fred`, `valyu/valyu-bls` filters,
but `("all", fast_mode=True)` already surfaces sec.gov/fred.stlouisfed.org via
web search (sufficient for v0 substance proof).

Path note: per BLOCKERS.md A8, lives at `smart_report/sources/` not the
brief's `backend/v2/sources/` to avoid mid-pivot refactor risk. Path naming
generic guidance; what matters is the architectural shape.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .base import CostEstimate, Finding, SearchBackend, SearchResult, Source
from .valyu import ValyuClient, ValyuResult, ValyuSearchError

_logger = logging.getLogger(__name__)


class ValyuAdapter:
    """Adapter making `ValyuClient` look like a SearchBackend.

    Constructor takes an optional injected `ValyuClient` for tests. Default
    instantiates one with the API key from `VALYU_API_KEY` environment
    variable (loaded via dotenv at app startup).
    """

    name = "valyu"
    is_primary_capable = True

    # Valyu fast-tier per-call cost (~$0.001-0.005 per result × ~10 results)
    # observed in Day 2 live smoke + Day 4 dry-run. Conservative point estimate
    # for budget planning.
    _COST_NOTE = "Valyu fast tier ~$0.005-0.030/call depending on dataset mix"
    _COST_PER_CALL_USD = 0.015

    def __init__(self, valyu_client: Optional[ValyuClient] = None) -> None:
        if valyu_client is None:
            api_key = os.environ.get("VALYU_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ValyuAdapter requires VALYU_API_KEY in env or an injected ValyuClient"
                )
            valyu_client = ValyuClient(api_key=api_key)
        self._client = valyu_client

    async def search(
        self,
        query: str,
        *,
        domain_hint: Optional[str] = None,
        max_results: int = 10,
        cost_budget_usd: Optional[float] = None,
    ) -> SearchResult:
        """Call Valyu DeepSearch and re-shape the response.

        `cost_budget_usd` is currently informational — Valyu fast tier per-call
        cost is bounded and we don't actively budget per-call. Future Step
        could enforce.
        """
        t0 = time.monotonic()
        _logger.info(
            "valyu.search start",
            extra={
                "valyu_query": query[:120],
                "valyu_domain_hint": domain_hint,
                "valyu_max_results": max_results,
            },
        )
        try:
            raw = await self._client.search(
                query,
                search_type="all",
                fast_mode=True,
                max_results=max_results,
            )
        except ValyuSearchError as e:
            latency_ms = int((time.monotonic() - t0) * 1000)
            _logger.warning(
                "valyu.search failed",
                extra={
                    "valyu_error": str(e),
                    "valyu_latency_ms": latency_ms,
                },
            )
            return SearchResult(
                findings=[],
                sources=[],
                raw_metadata={"domain_hint": domain_hint, "max_results": max_results},
                cost_usd=self._COST_PER_CALL_USD,  # Valyu charges even on errors per Day 2 finding
                latency_ms=latency_ms,
                is_empty_or_error=True,
                error=f"ValyuSearchError: {e}",
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        sources, findings = self._map_raw(raw)
        # Valyu charges per-result; sum actual prices instead of using estimate
        cost_usd = sum(r.price for r in raw) if raw else self._COST_PER_CALL_USD * 0.1
        is_empty = not findings and not sources

        _logger.info(
            "valyu.search ok",
            extra={
                "valyu_result_count": len(raw),
                "valyu_source_count": len(sources),
                "valyu_finding_count": len(findings),
                "valyu_cost_usd": round(cost_usd, 4),
                "valyu_latency_ms": latency_ms,
            },
        )

        return SearchResult(
            findings=findings,
            sources=sources,
            raw_metadata={
                "domain_hint": domain_hint,
                "max_results": max_results,
                "raw_count": len(raw),
            },
            cost_usd=cost_usd,
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

    def _map_raw(self, raw: list[ValyuResult]) -> tuple[list[Source], list[Finding]]:
        """Map `list[ValyuResult]` from `ValyuClient` to Source + Finding lists.

        Each ValyuResult becomes a Source. For findings, we treat the result's
        content as one finding citing that source — a Valyu DeepSearch result
        IS already a synthesised snippet, so 1:1 mapping is correct (vs
        Perplexity which may return multiple distinct claims per source).
        """
        if not raw:
            return ([], [])

        sources: list[Source] = []
        findings: list[Finding] = []
        by_url: dict[str, Source] = {}

        for vr in raw:
            url = vr.url or ""
            if not url:
                continue
            src = by_url.get(url)
            if src is None:
                src = Source(
                    url=url,
                    title=vr.title or None,
                    snippet=(vr.content or "")[:400] if vr.content else None,
                    backend=self.name,
                    raw_metadata={
                        "valyu_source": vr.source,  # dataset id e.g. "valyu/valyu-fred"
                        "publication_date": vr.publication_date,
                        "data_type": vr.data_type,
                        "relevance_score": vr.relevance_score,
                        "price": vr.price,
                        # Pass through Valyu's own metadata dict for downstream consumers
                        "valyu_metadata": vr.metadata,
                    },
                    quality_tier=None,  # Step 3.3 classifier owns this
                )
                by_url[url] = src
                sources.append(src)
            if vr.content:
                findings.append(
                    Finding(
                        text=vr.content,
                        sources=[src],
                        raw_metadata={
                            "valyu_source": vr.source,
                            "relevance_score": vr.relevance_score,
                        },
                    )
                )

        return (sources, findings)
