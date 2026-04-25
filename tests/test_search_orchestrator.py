"""Tests for v4.5 week-7 Day 3 — domain routing + SearchOrchestrator.

Two test groups:
  1. Routing decisions — pure mapping from QueryDomain to BackendPlan
     (5 tests, one per non-trivial domain).
  2. Orchestrator dispatch — including the primary→fallback path
     when Valyu primary fails (1 integration test).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from smart_report.domain_detector import (
    BACKEND_PLAN_BY_DOMAIN,
    Backend,
    QueryDomain,
    backend_plan_for,
    detect_query_domain,
)
from smart_report.sources.orchestrator import SearchOrchestrator
from smart_report.sources.valyu import ValyuResult, ValyuSearchError


# ---------------------------------------------------------------------------
# Routing decisions — domain → BackendPlan
# ---------------------------------------------------------------------------


def test_routing_eu_regulatory_uses_proprietary_valyu_primary():
    """EU regulatory queries hit Valyu's value-add proprietary corpus.

    The plan must request search_type='proprietary' + fast_mode=False
    (closes BLOCKERS.md A3 risk: a 'proprietary + fast' combo would
    silently fall back to web search).
    """
    plan = backend_plan_for(
        "EU CRCF directive obligations for member states 2026"
    )
    assert plan.primary is Backend.VALYU
    assert plan.fallback is Backend.PERPLEXITY_MANUAL
    assert plan.valyu_spec is not None
    assert plan.valyu_spec.search_type == "proprietary"
    assert plan.valyu_spec.fast_mode is False


def test_routing_ru_real_estate_skips_valyu_entirely():
    """Russian RE: nothing useful in Valyu's corpus per Day 1 capability map.

    Plan must be PERPLEXITY_MANUAL primary with NO fallback — calling
    Valyu would just burn budget on irrelevant English-only sources.
    """
    plan = backend_plan_for(
        "Анализ рынка элитной недвижимости Москвы 2026"
    )
    assert plan.primary is Backend.PERPLEXITY_MANUAL
    assert plan.fallback is None
    assert detect_query_domain(
        "Анализ рынка элитной недвижимости Москвы 2026"
    ) is QueryDomain.RU_REAL_ESTATE


def test_routing_ru_automotive_skips_valyu_entirely():
    """Same logic as RU_RE — Russian automotive sources (Автостат /
    Минпромторг / АЕБ) aren't in Valyu, so manual Perplexity is the
    only viable path."""
    plan = backend_plan_for(
        "Локализация электромобилей в России: AvtoVAZ vs Evolute"
    )
    assert plan.primary is Backend.PERPLEXITY_MANUAL
    assert plan.fallback is None


def test_routing_global_tech_uses_perplexity_primary_valyu_fallback():
    """Vendor blogs / changelogs — Perplexity has better recall.
    Valyu fallback as cheap arxiv acceleration (search_type='all',
    fast_mode=True is API-compatible)."""
    plan = backend_plan_for(
        "Comparative observability tooling for LLM applications: langfuse vs helicone"
    )
    assert plan.primary is Backend.PERPLEXITY_MANUAL
    assert plan.fallback is Backend.VALYU
    assert plan.valyu_spec is not None
    assert plan.valyu_spec.search_type == "all"
    assert plan.valyu_spec.fast_mode is True


def test_routing_generic_default_falls_back_to_cheap_valyu():
    """Generic queries: no strong signal either way. Manual Perplexity
    primary (broad recall), cheap Valyu fallback if PPLX returns
    nothing useful (handled by caller for the manual case; for the
    auto fallback path Valyu fires fast/web)."""
    plan = backend_plan_for("brief overview of solar panel efficiency improvements")
    assert plan.primary is Backend.PERPLEXITY_MANUAL
    assert plan.fallback is Backend.VALYU
    assert plan.valyu_spec is not None
    assert plan.valyu_spec.fast_mode is True


def test_routing_table_covers_every_known_domain():
    """If a new QueryDomain is added without a routing rule, this
    should fail loudly — silent KeyError at runtime would be worse."""
    for domain in QueryDomain:
        assert domain in BACKEND_PLAN_BY_DOMAIN, f"missing plan for {domain}"


# ---------------------------------------------------------------------------
# Orchestrator dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_returns_handoff_for_manual_primary():
    """Manual Perplexity primary → handoff_required, no Valyu call."""
    valyu = MagicMock()
    valyu.search = AsyncMock()
    orch = SearchOrchestrator(valyu_client=valyu)
    outcome = await orch.search(
        "Анализ рынка элитной недвижимости Москвы 2026"
    )
    assert outcome.backend is Backend.PERPLEXITY_MANUAL
    assert outcome.handoff_required is True
    assert outcome.results == []
    assert outcome.fallback_used is False
    valyu.search.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_calls_valyu_with_routing_kwargs_for_eu_reg():
    """EU regulatory must invoke Valyu with proprietary + fast=False
    (the routing rule, not the client default)."""
    valyu = MagicMock()
    valyu.search = AsyncMock(return_value=[
        ValyuResult(
            url="https://eur-lex.europa.eu/foo",
            title="CRCF",
            content="...",
            source="valyu/valyu-eu-regulatory",
            price=0.01,
        ),
    ])
    orch = SearchOrchestrator(valyu_client=valyu)
    outcome = await orch.search(
        "EU CRCF directive obligations for member states 2026"
    )
    assert outcome.backend is Backend.VALYU
    assert outcome.handoff_required is False
    assert outcome.fallback_used is False
    assert len(outcome.results) == 1
    kwargs = valyu.search.call_args.kwargs
    assert kwargs["search_type"] == "proprietary"
    assert kwargs["fast_mode"] is False


@pytest.mark.asyncio
async def test_orchestrator_falls_back_when_valyu_primary_returns_empty():
    """EU reg query: Valyu returns no hits → orchestrator surfaces the
    manual Perplexity fallback with fallback_used=True so the caller
    knows the primary was tried."""
    valyu = MagicMock()
    valyu.search = AsyncMock(return_value=[])
    orch = SearchOrchestrator(valyu_client=valyu)
    outcome = await orch.search(
        "EU CRCF directive obligations for member states 2026"
    )
    assert outcome.backend is Backend.PERPLEXITY_MANUAL
    assert outcome.handoff_required is True
    assert outcome.fallback_used is True
    assert outcome.primary_error == "empty_results"
    valyu.search.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_falls_back_when_valyu_primary_raises():
    """EU reg query: Valyu raises ValyuSearchError (e.g. retries
    exhausted) → orchestrator catches, falls back to manual Perplexity,
    records the error reason."""
    valyu = MagicMock()
    valyu.search = AsyncMock(side_effect=ValyuSearchError("retries exhausted"))
    orch = SearchOrchestrator(valyu_client=valyu)
    outcome = await orch.search(
        "EU CRCF directive obligations for member states 2026"
    )
    assert outcome.backend is Backend.PERPLEXITY_MANUAL
    assert outcome.handoff_required is True
    assert outcome.fallback_used is True
    assert outcome.primary_error is not None
    assert "valyu_error" in outcome.primary_error


@pytest.mark.asyncio
async def test_orchestrator_no_fallback_for_ru_domains_when_primary_is_manual():
    """RU RE has no fallback. Even if PPLX manual loop comes back
    empty (out of scope for this layer), orchestrator must NOT try
    Valyu — Day 1 finding said Russian sources aren't there."""
    valyu = MagicMock()
    valyu.search = AsyncMock()
    orch = SearchOrchestrator(valyu_client=valyu)
    outcome = await orch.search(
        "Девелоперы новостроек бизнес-класса Москвы 2026"
    )
    assert outcome.backend is Backend.PERPLEXITY_MANUAL
    assert outcome.handoff_required is True
    assert outcome.fallback_used is False
    valyu.search.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_does_not_require_valyu_client_for_pure_manual_routes():
    """If a deployment doesn't have a Valyu key configured, RU queries
    should still work — they never hit Valyu. Only when a route would
    need Valyu and the client is absent do we expect to blow up."""
    orch = SearchOrchestrator(valyu_client=None)
    outcome = await orch.search(
        "Анализ рынка элитной недвижимости Москвы 2026"
    )
    assert outcome.backend is Backend.PERPLEXITY_MANUAL
    assert outcome.handoff_required is True


@pytest.mark.asyncio
async def test_orchestrator_raises_when_route_needs_valyu_but_client_missing():
    """EU regulatory route → wants Valyu → no client injected → blow
    up with a clear message rather than silently dropping data."""
    orch = SearchOrchestrator(valyu_client=None)
    with pytest.raises(RuntimeError, match="no ValyuClient was injected"):
        await orch.search(
            "EU CRCF directive obligations for member states 2026"
        )
