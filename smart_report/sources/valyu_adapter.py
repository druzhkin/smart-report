"""Valyu adapter implementing SearchBackend Protocol (M1 D1 B1.2 of two-week brief).

Wraps the existing `ValyuClient` (Day 2 work) and re-shapes its `list[ValyuResult]`
output to the shared `SearchResult` shape from `smart_report.sources.base`.

Current production behavior routes by declared domain: scientific, medical, and
technical research requests use proprietary Valyu datasets and disable fast mode
so paper sources are not silently replaced by generic web search. Financial and
general requests keep the broader `all` search path unless the orchestrator
provides a more specific included-source policy.

Per v3 §0 architectural invariant + `tests/test_routing_invariants.py`:
`is_primary_capable = True` — Valyu is the ONLY backend allowed to be primary
on covered domains.

Path note: per BLOCKERS.md A8, lives at `smart_report/sources/` not the
brief's `backend/v2/sources/` to avoid mid-pivot refactor risk. Path naming
generic guidance; what matters is the architectural shape.
"""

from __future__ import annotations

import logging
import os
import time

from .base import CostEstimate, Finding, SearchResult, Source
from .valyu import ValyuClient, ValyuResult, ValyuSearchError

_logger = logging.getLogger(__name__)

_SCIENTIFIC_VALYU_SOURCES = [
    "valyu/valyu-arxiv",
    "valyu/valyu-pubmed",
    "valyu/valyu-biorxiv",
    "valyu/valyu-medrxiv",
]
_MEDICAL_VALYU_SOURCES = [
    "valyu/valyu-pubmed",
    "valyu/valyu-medrxiv",
    "valyu/valyu-clinical-trials",
]
_TECHNICAL_RESEARCH_VALYU_SOURCES = ["valyu/valyu-arxiv"]


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

    def __init__(self, valyu_client: ValyuClient | None = None) -> None:
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
        domain_hint: str | None = None,
        max_results: int = 10,
        cost_budget_usd: float | None = None,
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
        policy = _policy_for_domain(domain_hint)
        try:
            raw = await self._client.search(
                query,
                search_type=policy["search_type"],  # type: ignore[arg-type]
                fast_mode=bool(policy["fast_mode"]),
                included_sources=policy["included_sources"],  # type: ignore[arg-type]
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
                "search_type": policy["search_type"],
                "fast_mode": policy["fast_mode"],
                "included_sources": policy["included_sources"],
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


def _policy_for_domain(domain_hint: str | None) -> dict[str, object]:
    """Return Valyu DeepSearch settings for the resolved research domain.

    Scientific and clinical routes must explicitly hit Valyu's paper datasets.
    Otherwise the product can claim that Valyu ran while still missing arXiv,
    PubMed, bioRxiv, or medRxiv coverage.
    """

    domain = str(domain_hint or "").lower().replace("-", "_").replace(" ", "_")
    included_sources: list[str] | None = None
    if "medical" in domain or "clinical" in domain or "biomedical" in domain:
        included_sources = _MEDICAL_VALYU_SOURCES
    elif "technical_research" in domain:
        included_sources = _TECHNICAL_RESEARCH_VALYU_SOURCES
    elif "scientific" in domain or "academic" in domain:
        included_sources = _SCIENTIFIC_VALYU_SOURCES

    if included_sources:
        return {
            "search_type": "proprietary",
            "fast_mode": False,
            "included_sources": included_sources,
        }
    return {"search_type": "all", "fast_mode": True, "included_sources": None}
