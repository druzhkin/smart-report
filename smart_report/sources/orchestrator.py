"""Domain-aware search orchestrator (v4.5 week-7 Day 3).

Thin layer above ``ValyuClient`` that picks the right backend per query
domain and falls through to the fallback backend on empty results or
transient Valyu errors. Per-domain routing is owned by
``smart_report.domain_detector.BACKEND_PLAN_BY_DOMAIN``; the orchestrator
itself is mechanical dispatch.

Honest-scope note: we have one auto-retrieve backend (Valyu) and one
"manual" backend (the v4 Perplexity DR loop driven by hand). When the
plan picks ``Backend.PERPLEXITY_MANUAL`` we don't call anything — we
return a ``SearchOutcome`` with that backend tag, empty results, and
``handoff_required=True`` so the caller knows to drive Perplexity.
A future sprint can drop in a real Perplexity client without changing
the orchestrator's surface — only the dispatch in ``_call_backend``.

Why not raise on Valyu errors here? Two backends exist precisely so one
can cover the other. The orchestrator catches ``ValyuSearchError`` and
falls through; only when both backends have been tried does the caller
see an exception (and only if the fallback also failed).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from smart_report.domain_detector import (
    Backend,
    BackendPlan,
    QueryDomain,
    ValyuCallSpec,
    backend_plan_for,
    detect_query_domain,
)
from smart_report.sources.valyu import (
    ValyuClient,
    ValyuResult,
    ValyuSearchError,
)

_logger = logging.getLogger(__name__)


@dataclass
class SearchOutcome:
    """Result of one orchestrated search, including which backend served it.

    ``handoff_required`` is True when the chosen backend is
    ``PERPLEXITY_MANUAL``; the caller drives the v4 manual DR loop in
    that case. ``fallback_used`` is True when the primary backend was
    skipped (no results / transient error) and we landed on the
    fallback.
    """

    backend: Backend
    domain: QueryDomain
    results: list[ValyuResult] = field(default_factory=list)
    handoff_required: bool = False
    fallback_used: bool = False
    primary_error: str | None = None


class SearchOrchestrator:
    """Dispatch a query to the right backend per its detected domain.

    Usage::

        orch = SearchOrchestrator(valyu_client=ValyuClient(api_key=...))
        outcome = await orch.search("Tesla Q4 2025 earnings")
        if outcome.handoff_required:
            # caller runs the manual Perplexity DR loop
            ...
        else:
            for r in outcome.results: ...

    The orchestrator is intentionally NOT responsible for:
      * caching (callers can wrap)
      * cost accounting (ValyuResult.price flows through; tally upstream)
      * Perplexity's manual loop (out of scope; surfaced via sentinel)
    """

    def __init__(
        self,
        *,
        valyu_client: ValyuClient | None = None,
        max_results: int = 10,
    ) -> None:
        self._valyu = valyu_client
        self._max_results = max_results

    async def search(self, query: str) -> SearchOutcome:
        domain = detect_query_domain(query)
        plan = backend_plan_for(query)
        return await self._run_plan(query, domain, plan)

    async def _run_plan(
        self, query: str, domain: QueryDomain, plan: BackendPlan
    ) -> SearchOutcome:
        outcome = await self._call_backend(query, domain, plan.primary, plan.valyu_spec)
        if _is_actionable(outcome) or plan.fallback is None:
            return outcome
        # Primary returned nothing useful and a fallback exists — try it.
        fallback_outcome = await self._call_backend(
            query, domain, plan.fallback, plan.valyu_spec
        )
        fallback_outcome.fallback_used = True
        fallback_outcome.primary_error = outcome.primary_error or _empty_reason(outcome)
        return fallback_outcome

    async def _call_backend(
        self,
        query: str,
        domain: QueryDomain,
        backend: Backend,
        valyu_spec: ValyuCallSpec | None,
    ) -> SearchOutcome:
        if backend is Backend.PERPLEXITY_MANUAL:
            return SearchOutcome(
                backend=Backend.PERPLEXITY_MANUAL,
                domain=domain,
                handoff_required=True,
            )
        if backend is Backend.VALYU:
            return await self._call_valyu(query, domain, valyu_spec)
        raise ValueError(f"Unknown backend: {backend!r}")  # pragma: no cover

    async def _call_valyu(
        self,
        query: str,
        domain: QueryDomain,
        spec: ValyuCallSpec | None,
    ) -> SearchOutcome:
        if self._valyu is None:
            raise RuntimeError(
                "SearchOrchestrator received a Valyu route but no ValyuClient was injected"
            )
        spec = spec or ValyuCallSpec()
        try:
            results = await self._valyu.search(
                query,
                search_type=spec.search_type,  # type: ignore[arg-type]
                category=spec.category,
                fast_mode=spec.fast_mode,
                included_sources=spec.included_sources,
                max_results=self._max_results,
                relevance_threshold=spec.relevance_threshold,
            )
            return SearchOutcome(
                backend=Backend.VALYU, domain=domain, results=results
            )
        except ValyuSearchError as e:
            _logger.warning("Valyu primary failed for domain %s: %s", domain, e)
            return SearchOutcome(
                backend=Backend.VALYU,
                domain=domain,
                results=[],
                primary_error=f"valyu_error: {e}",
            )


def _is_actionable(outcome: SearchOutcome) -> bool:
    """An outcome is actionable when the caller can use it without falling back.

    Manual handoff counts as actionable — the caller knows what to do.
    Empty Valyu results do NOT count: the whole point of the
    primary→fallback shape is to recover from a Valyu miss.
    """
    if outcome.handoff_required:
        return True
    if outcome.primary_error is not None:
        return False
    return len(outcome.results) > 0


def _empty_reason(outcome: SearchOutcome) -> str:
    if outcome.primary_error:
        return outcome.primary_error
    return "empty_results"
