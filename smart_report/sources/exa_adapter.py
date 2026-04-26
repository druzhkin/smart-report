"""Exa adapter implementing SearchBackend Protocol.

Wraps `ExaClient` and re-shapes its `list[ExaResult]` to the shared
`SearchResult` shape. Per v3 §0: `is_primary_capable = False` —
augment for technical_research / scientific where Valyu's arxiv is
solid but semantic similarity adds value.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .base import CostEstimate, Finding, SearchBackend, SearchResult, Source
from .exa import ExaClient, ExaResult, ExaSearchError

_logger = logging.getLogger(__name__)


class ExaAdapter:
    name = "exa"
    is_primary_capable = False

    _COST_NOTE = "Exa auto/fast ~$0.005-0.020/call; deep-lite ~$0.020-0.050"
    _COST_PER_CALL_USD = 0.012  # conservative midpoint for auto

    def __init__(self, client: Optional[ExaClient] = None) -> None:
        if client is None:
            api_key = os.environ.get("EXA_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ExaAdapter requires EXA_API_KEY in env or an injected ExaClient"
                )
            client = ExaClient(api_key=api_key)
        self._client = client

    async def search(
        self,
        query: str,
        *,
        domain_hint: Optional[str] = None,
        max_results: int = 10,
        cost_budget_usd: Optional[float] = None,
    ) -> SearchResult:
        t0 = time.monotonic()
        _logger.info(
            "exa.search start", extra={
                "exa_query": query[:120],
                "exa_domain_hint": domain_hint,
            },
        )
        try:
            raw = await self._client.search(query, type="auto", num_results=max_results)
        except ExaSearchError as e:
            latency_ms = int((time.monotonic() - t0) * 1000)
            _logger.warning("exa.search failed: %s", e)
            return SearchResult(
                findings=[], sources=[], raw_metadata={"domain_hint": domain_hint},
                cost_usd=0.0, latency_ms=latency_ms,
                is_empty_or_error=True,
                error=f"ExaSearchError: {e}",
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        sources, findings = self._map_raw(raw)
        is_empty = not findings and not sources

        _logger.info(
            "exa.search ok", extra={
                "exa_result_count": len(raw),
                "exa_cost_usd": self._COST_PER_CALL_USD,
                "exa_latency_ms": latency_ms,
            },
        )
        return SearchResult(
            findings=findings, sources=sources,
            raw_metadata={"domain_hint": domain_hint, "raw_count": len(raw)},
            cost_usd=self._COST_PER_CALL_USD, latency_ms=latency_ms,
            is_empty_or_error=is_empty,
        )

    @property
    def cost_per_call(self) -> CostEstimate:
        return CostEstimate(per_call_usd=self._COST_PER_CALL_USD, notes=self._COST_NOTE)

    def _map_raw(self, raw: list[ExaResult]) -> tuple[list[Source], list[Finding]]:
        if not raw:
            return ([], [])
        sources: list[Source] = []
        findings: list[Finding] = []
        by_url: dict[str, Source] = {}
        for er in raw:
            url = er.url or ""
            if not url:
                continue
            src = by_url.get(url)
            if src is None:
                # Prefer highlights (focused) over full text (verbose) for snippet
                snippet = er.highlights[0] if er.highlights else (er.text or "")[:400]
                src = Source(
                    url=url,
                    title=er.title or None,
                    snippet=snippet,
                    backend=self.name,
                    raw_metadata={
                        "score": er.score,
                        "published_date": er.published_date,
                        "author": er.author,
                        "highlights": er.highlights,
                    },
                    quality_tier=None,
                )
                by_url[url] = src
                sources.append(src)
            text = er.text or (er.highlights[0] if er.highlights else "")
            if text:
                findings.append(
                    Finding(text=text, sources=[src], raw_metadata={"score": er.score}),
                )
        return (sources, findings)
