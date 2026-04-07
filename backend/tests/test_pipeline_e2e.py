"""End-to-end integration tests for the full 17-node LangGraph pipeline.

Requires OPENROUTER_API_KEY in .env (or already exported to the environment).
Run explicitly:
    pytest -m integration backend/tests/test_pipeline_e2e.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Load real API key from .env BEFORE any backend imports so that
# pydantic-settings picks up the real key when it instantiates Settings().
# ---------------------------------------------------------------------------
try:
    from dotenv import dotenv_values as _dotenv_values

    _env_path = Path(__file__).resolve().parents[2] / ".env"
    if _env_path.exists():
        _dotenv = _dotenv_values(str(_env_path))
        for _k, _v in _dotenv.items():
            if _v is not None:
                os.environ.setdefault(_k, _v)  # don't override explicit shell exports
        # Always force the real key (override conftest's "test-key" setdefault)
        if _real_key := _dotenv.get("OPENROUTER_API_KEY"):
            os.environ["OPENROUTER_API_KEY"] = _real_key
except ImportError:
    pass  # python-dotenv optional; rely on shell environment

import pytest
import respx
from httpx import Response
from langgraph.checkpoint.memory import MemorySaver

from backend.pipeline.cost_guard import BudgetExceededError
from backend.pipeline.graph import build_graph
from backend.pipeline.model_router import AgentTask
from backend.pipeline.state import AgentState
from backend.schemas.intake import IntakeResult
from backend.schemas.master_prompt import MasterPrompt, RouterResult
from backend.schemas.research_result import ParallelBatches
from backend.schemas.quality import ResearchCritiqueResult


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_ID = "test-e2e-001"
QUERY = "Анализ рынка ИИ в России"

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
CITE_URL_1 = "https://ai-analytics.example.test/russia-2024"
CITE_URL_2 = "https://sber-research.example.test/gigachat"

_PERPLEXITY_CONTENT = (
    "Рынок искусственного интеллекта в России демонстрирует устойчивый рост.\n\n"
    "По оценкам аналитиков, объём рынка ИИ составил $2.5 млрд в 2024 году, "
    "что на 35% больше показателей предыдущего года.\n\n"
    "Ключевые игроки: Сбер (GigaChat, Kandinsky), "
    "Яндекс (YandexGPT, Алиса), VK Group.\n\n"
    "Государственные инвестиции в ИИ — 100 млрд рублей до 2025 года."
)

PERPLEXITY_RESP = {
    "choices": [{"message": {"content": _PERPLEXITY_CONTENT}}],
    "citations": [
        {
            "url": CITE_URL_1,
            "title": "Russia AI Market 2024",
            "snippet": "Russian AI market grew 35% to $2.5 billion in 2024",
        },
        {
            "url": CITE_URL_2,
            "title": "Sber GigaChat Analysis",
            "snippet": "Sber holds 40% of Russian LLM market with GigaChat",
        },
    ],
    "usage": {"prompt_tokens": 250, "completion_tokens": 500},
}

# Large usage so research cost pushes over a tight budget in test 3.
PERPLEXITY_RESP_EXPENSIVE = {
    **PERPLEXITY_RESP,
    "usage": {"prompt_tokens": 50_000, "completion_tokens": 50_000},
}

_PAGE_HTML = (
    "<html><body>"
    "Russian AI market grew 35% to $2.5 billion in 2024. "
    "Sber holds leading position with GigaChat. "
    "Government investing 100 billion rubles in AI through 2025. "
    "Yandex and VK are major players in Russian AI landscape. "
    + " artificial intelligence " * 50
    + "</body></html>"
)

# Plain text returned by _fetch_content (after HTML stripping).
_CITE_PAGE_TEXT = (
    "Russian AI market grew 35% to 2.5 billion dollars in 2024. "
    "Sber GigaChat dominates Russian LLM market. "
    "Government investing 100 billion rubles in AI through 2025. "
    * 3
)

_QA_REVISE_VISUAL = json.dumps({
    "score": 0.5,
    "issues": [
        {
            "category": "completeness",
            "severity": "major",
            "location": "Section 2",
            "description": "Market data incomplete",
            "suggestion": "Add quantitative market share data",
        }
    ],
})
_QA_REVISE_SUBSTANCE = json.dumps({
    "score": 0.5,
    "issues": [
        {
            "category": "factual",
            "severity": "major",
            "location": "intro",
            "description": "Missing primary sources",
            "suggestion": "Cite government statistics",
        }
    ],
    "citation_score": 0.4,
})
_QA_PASS_VISUAL = json.dumps({"score": 0.9, "issues": []})
_QA_PASS_SUBSTANCE = json.dumps({"score": 0.9, "issues": [], "citation_score": 0.9})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _initial_state(cost_usd: float = 0.0) -> AgentState:
    return {
        "session_id": SESSION_ID,
        "original_request": QUERY,
        "user_request": {"query": QUERY},
        "cost_usd": cost_usd,
        "revision_count": 0,
        "iteration": 1,
        "max_iterations": 3,
        "messages": [],
        "errors": [],
    }


def _aiohttp_session_mock(status: int = 200, content: str = _PAGE_HTML) -> MagicMock:
    """Return a mock that mimics aiohttp.ClientSession async context manager."""
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=content)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _graph_config() -> dict:
    return {"configurable": {"thread_id": SESSION_ID}}


def _visited_nodes(history: list) -> set[str]:
    """Extract node names from LangGraph checkpoint history metadata."""
    visited: set[str] = set()
    for snap in history:
        metadata = getattr(snap, "metadata", None) or {}
        if isinstance(metadata, dict):
            writes = metadata.get("writes", {})
            if isinstance(writes, dict):
                visited.update(str(k) for k in writes.keys())

        values = getattr(snap, "values", None) or {}
        if isinstance(values, dict):
            agent = values.get("current_agent")
            if isinstance(agent, str) and agent:
                visited.add(agent)
                if agent in {"renderer", "presentation"}:
                    visited.add("render_and_present")
                if agent == "cost_guard":
                    visited.add("cost_guard_post_intake")
                    visited.add("cost_guard_post_research")

    # Normalise known aliases from agent-level names to graph node names.
    if "presentation" in visited or "renderer" in visited:
        visited.add("render_and_present")
    return visited


# ---------------------------------------------------------------------------
# Common patches applied to every test in this module
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_stores():
    """Prevent SQLite writes to ./data/ during tests."""
    import backend.knowledge_library.facts_store as _fs
    import backend.knowledge_library.sources_store as _ss

    with (
        patch.object(_fs.facts_store, "save_verified_facts", AsyncMock(return_value=None)),
        patch.object(_fs.facts_store, "get_by_session", AsyncMock(return_value=[])),
        patch.object(_ss.sources_store, "upsert_sources", AsyncMock(return_value=None)),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_sleep():
    with patch("asyncio.sleep", return_value=None):
        yield


@pytest.fixture(autouse=True)
def _patch_presentation_services():
    """Skip real Presenton/Gamma HTTP calls — they waste 30s on retries."""
    with (
        patch(
            "backend.agents.presentation_agent._presenton_create",
            AsyncMock(side_effect=Exception("presenton mocked")),
        ),
        patch(
            "backend.agents.presentation_agent._gamma_create",
            AsyncMock(side_effect=Exception("gamma mocked")),
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_embedder():
    """Mock sentence-transformers embedder (heavy dep, not installed in CI)."""
    import numpy as np

    mock_embedder = MagicMock()
    # Return two near-identical unit vectors so cosine similarity ≈ 1.0 (VERIFIED).
    mock_embedder.encode = MagicMock(
        return_value=np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    )
    with patch("backend.agents.citation_verifier._get_embedder", return_value=mock_embedder):
        yield



# ---------------------------------------------------------------------------
# TEST 1 — Full pipeline, happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline_all_layers():
    """Full 17-node pipeline with real OpenRouter; Perplexity + citation checks mocked."""
    cfg = _graph_config()

    # Patch Perplexity and citation functions directly so real OpenRouter calls
    # pass through unimpeded (respx.mock would block all httpx in 0.22).
    with (
        patch(
            "backend.agents.research_agent._call_perplexity",
            AsyncMock(return_value=PERPLEXITY_RESP),
        ),
        patch(
            "backend.agents.citation_verifier._head_check",
            AsyncMock(return_value=True),
        ),
        patch(
            "backend.agents.citation_verifier._fetch_content",
            AsyncMock(return_value=_CITE_PAGE_TEXT),
        ),
        patch("aiohttp.ClientSession", return_value=_aiohttp_session_mock()),
    ):
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        result: AgentState = await graph.ainvoke(_initial_state(), config=cfg)

    # 1. Final verdict should reach a terminal state.
    # With real LLM-backed QA this can legitimately be PASS or REJECT depending
    # on model variance; this test validates full pipeline traversal.
    verdict = result.get("verdict")
    assert verdict in {"PASS", "REJECT"}, f"Expected terminal verdict, got {verdict}"

    # 2. master_prompt headers
    mp = result.get("master_prompt")
    assert mp is not None, "master_prompt is missing from final state"
    mp_text = mp.master_prompt
    for header in ("## PROFILE", "## KNOWLEDGE", "## REASONING", "## RELIABILITY"):
        assert header in mp_text, f"master_prompt missing header: {header}"

    # 3. Research results
    assert len(result.get("research_results", [])) >= 1

    # 4. Cost tracked
    assert result.get("cost_usd", 0.0) > 0.0

    # 5. HTML or PDF output exists
    paths = result.get("final_report_paths") or []
    assert any(
        p.endswith(".html") or p.endswith(".pdf") for p in paths
    ), f"No html/pdf in final_report_paths: {paths}"

    # 6. Revision count within bounds
    assert result.get("revision_count", 0) <= 3

    # 7. Node coverage via checkpoint history
    history = [s async for s in graph.aget_state_history(cfg)]
    visited = _visited_nodes(history)
    expected = {
        "intake",
        "cost_guard_post_intake",
        "prompt_router",
        "prompt_king",
        "prompt_splitter",
        "supervisor",
        "research",
        "cost_guard_post_research",
        "summarization",
        "reflect",
        "citation_verifier",
        "research_critique",
        "synthesis_gate",
        "viz_agent",
        "render_and_present",
        "qa",
        "save_to_knowledge_library",
    }
    missing = expected - visited
    assert not missing, f"Nodes not visited: {missing}"


# ---------------------------------------------------------------------------
# TEST 2 — QA returns REVISE first, then PASS; renderer called twice
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_pipeline_revise_then_pass():
    """QA REVISE on round 1, PASS on round 2; renderer called exactly twice."""
    cfg = _graph_config()

    # Track QA call rounds and render invocations.
    qa_round: dict[str, int] = {"count": 0}
    render_count: dict[str, int] = {"n": 0}

    async def _mock_visual_qa(system, report_json, chart_paths, model):
        qa_round["count"] += 1
        if qa_round["count"] == 1:
            return _QA_REVISE_VISUAL
        return _QA_PASS_VISUAL

    async def _mock_substance_qa(system, report_json, model):
        # count is already incremented by visual_qa (they run concurrently but
        # asyncio is single-threaded; visual_qa coroutine finishes first).
        if qa_round["count"] == 1:
            return _QA_REVISE_SUBSTANCE
        return _QA_PASS_SUBSTANCE

    # Wrap render_and_present to count invocations.
    import backend.pipeline.graph as _graph_mod

    original_render = _graph_mod.render_and_present

    async def _counted_render(state: AgentState) -> dict:
        render_count["n"] += 1
        return await original_render(state)

    with (
        patch(
            "backend.agents.research_agent._call_perplexity",
            AsyncMock(return_value=PERPLEXITY_RESP),
        ),
        patch(
            "backend.agents.citation_verifier._head_check",
            AsyncMock(return_value=True),
        ),
        patch(
            "backend.agents.citation_verifier._fetch_content",
            AsyncMock(return_value=_CITE_PAGE_TEXT),
        ),
        patch("aiohttp.ClientSession", return_value=_aiohttp_session_mock()),
        patch(
            "backend.pipeline.graph.run_research_critique",
            AsyncMock(
                return_value={
                    "research_critique_result": ResearchCritiqueResult(
                        verdict="ACCEPT",
                        overall_score=0.95,
                        blocking_issues=[],
                    )
                }
            ),
        ),
        patch("backend.agents.qa_agent._call_visual_qa", side_effect=_mock_visual_qa),
        patch("backend.agents.qa_agent._call_substance_qa", side_effect=_mock_substance_qa),
        patch("backend.pipeline.graph.render_and_present", _counted_render),
    ):
        state = _initial_state()
        state["max_iterations"] = 5
        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)
        result: AgentState = await graph.ainvoke(state, config=cfg)

    # revision_count == 1 (set by research_critique_node; QA loop doesn't add more)
    assert result.get("revision_count") == 1, (
        f"Expected revision_count=1, got {result.get('revision_count')}"
    )

    # Final verdict PASS
    assert result.get("verdict") == "PASS"

    # Renderer was called twice (once before first QA, once after REVISE)
    assert render_count["n"] == 2, (
        f"Expected render_and_present called 2×, got {render_count['n']}"
    )


# ---------------------------------------------------------------------------
# TEST 3 — Budget exceeded triggers BudgetExceededError before render
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_pipeline_budget_exceeded():
    """CostGuard raises BudgetExceededError at cost_guard_post_research."""
    from backend.config import settings

    budget = settings.budget_light  # 0.50 USD default
    initial_cost = budget * 0.9    # 0.45 — 90% pre-loaded

    # Force _get_budget to always return budget_light regardless of complexity.
    render_called: list[bool] = []

    # Build a minimal intake result that downstream agents can use.
    _intake_result = IntakeResult(
        original_query=QUERY,
        cleaned_query=QUERY,
        intent="research",
        domain="tech",
        complexity="low",
        depth="light",
        key_entities=["ИИ", "Россия"],
    )
    _master_prompt = MasterPrompt(
        system_prompt="Analyze AI market in Russia",
        user_prompt=QUERY,
        master_prompt=(
            "## PROFILE\nSenior analyst\n"
            "## KNOWLEDGE\nAI market research\n"
            "## REASONING\nData-driven analysis\n"
            "## RELIABILITY\nVerified sources only"
        ),
    )

    with (
        patch(
            "backend.pipeline.graph._get_budget",
            return_value=budget,
        ),
        patch(
            "backend.pipeline.graph.run_intake",
            AsyncMock(return_value={
                "intake_result": _intake_result,
                "cost_usd": initial_cost,
                "current_agent": "intake",
                "status": "prompting",
            }),
        ),
        patch(
            "backend.pipeline.graph.run_prompt_router",
            AsyncMock(return_value={
                "router_result": RouterResult(
                    task_type="research",
                    techniques=["chain_of_thought"],
                ),
                "selected_techniques": ["chain_of_thought"],
                "current_agent": "prompt_router",
            }),
        ),
        patch(
            "backend.pipeline.graph.run_prompt_king",
            AsyncMock(return_value={
                "master_prompt": _master_prompt,
                "current_agent": "prompt_king",
            }),
        ),
        patch(
            "backend.pipeline.graph.run_prompt_splitter",
            AsyncMock(return_value={
                "data_queries": [QUERY],
                "parallel_batches": ParallelBatches(),
                "current_agent": "prompt_splitter",
            }),
        ),
        patch(
            "backend.pipeline.graph.run_supervisor",
            AsyncMock(return_value={
                "data_queries": [QUERY],
                "current_agent": "supervisor",
            }),
        ),
        patch(
            "backend.pipeline.graph.render_and_present",
            AsyncMock(side_effect=lambda _s: render_called.append(True)),
        ),
        # All httpx intercepted — no real HTTP (tests budget logic only).
        respx.mock(assert_all_called=False) as mock,
    ):
        # Expensive Perplexity response pushes cost well over budget.
        perplexity_route = mock.post(PERPLEXITY_URL).mock(
            return_value=Response(200, json=PERPLEXITY_RESP_EXPENSIVE)
        )

        checkpointer = MemorySaver()
        graph = build_graph(checkpointer=checkpointer)

        with pytest.raises(BudgetExceededError):
            await graph.ainvoke(_initial_state(cost_usd=initial_cost), config=_graph_config())

        # Perplexity was called (research ran) but nothing after cost_guard_post_research.
        assert perplexity_route.called, "Perplexity must have been called (research ran)"

    # Pipeline must have stopped before render.
    assert not render_called, "render_and_present must not execute after BudgetExceededError"
