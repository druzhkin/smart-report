from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from langgraph.graph import END, StateGraph
from loguru import logger

from backend.agents.citation_verifier import run_citation_verifier
from backend.agents.intake_agent import run_intake
from backend.agents.presentation_agent import run_presentation
from backend.agents.prompt_king import run_prompt_king
from backend.agents.prompt_router import run_prompt_router
from backend.agents.prompt_splitter import run_prompt_splitter
from backend.agents.qa_agent import run_qa
from backend.agents.renderer import run_renderer
from backend.agents.research_agent import run_research
from backend.agents.research_critique_agent import run_research_critique
from backend.agents.reflect_agent import run_reflect
from backend.agents.summarization_agent import run_summarization
from backend.agents.supervisor_agent import run_supervisor
from backend.agents.viz_agent import run_viz_agent
from backend.config import normalize_database_url, settings
from backend.pipeline.cost_guard import BudgetExceededError, InsufficientEvidenceError
from backend.pipeline.state import AgentState


def _get_budget(state: AgentState) -> float:
    selected_depth = state.get("selected_depth")
    if selected_depth in {"light", "standard", "deep", "exhaustive"}:
        return {
            "light": settings.budget_light,
            "standard": settings.budget_standard,
            "deep": settings.budget_deep,
            "exhaustive": settings.budget_exhaustive,
        }[selected_depth]

    intake = state.get("intake_result")
    intake_depth = intake.depth if intake else None
    if intake_depth in {"light", "standard", "deep", "exhaustive"}:
        return {
            "light": settings.budget_light,
            "standard": settings.budget_standard,
            "deep": settings.budget_deep,
            "exhaustive": settings.budget_exhaustive,
        }[intake_depth]

    return settings.budget_standard


async def cost_guard_post_intake(state: AgentState) -> dict:
    budget = _get_budget(state)
    cost = state.get("cost_usd", 0.0)
    logger.info(f"CostGuard post-intake: ${cost:.4f} / ${budget:.2f}")
    if cost > budget:
        raise BudgetExceededError(
            f"Budget exceeded after intake: ${cost:.4f} > ${budget:.2f}"
        )
    return {"current_agent": "cost_guard"}


async def cost_guard_post_research(state: AgentState) -> dict:
    budget = _get_budget(state)
    cost = state.get("cost_usd", 0.0)
    total_sources = sum(len(result.sources) for result in list(state.get("research_results", []) or []))
    revision_count = state.get("revision_count", 0)
    logger.info(f"CostGuard post-research: ${cost:.4f} / ${budget:.2f}")
    if total_sources == 0 and revision_count <= 0:
        raise InsufficientEvidenceError(
            "Research returned 0 sources on the first pass; aborting instead of expanding unsupported branches"
        )
    if cost > budget:
        raise BudgetExceededError(
            f"Budget exceeded after research: ${cost:.4f} > ${budget:.2f}"
        )
    return {"current_agent": "cost_guard"}


async def render_and_present(state: AgentState) -> dict:
    base_cost = state.get("cost_usd", 0.0)

    render_res = await run_renderer(state)
    r_cost = render_res.get("cost_usd", base_cost) - base_cost

    pres_state = dict(state)
    pres_state["report"] = render_res.get("report")
    pres_state["chart_paths"] = state.get("chart_paths", [])
    pres_res = await run_presentation(pres_state)
    p_cost = pres_res.get("cost_usd", base_cost) - base_cost

    result: dict = {
        "report": render_res.get("report"),
        "final_report_paths": render_res.get("final_report_paths", []),
        "messages": pres_res.get("messages", state.get("messages", [])),
        "cost_usd": base_cost + r_cost + p_cost,
        "current_agent": "render_and_present",
        "status": "rendering",
    }
    if pres_res.get("presentation_url"):
        result["presentation_url"] = pres_res["presentation_url"]
    if pres_res.get("presentation_path"):
        result["presentation_path"] = pres_res["presentation_path"]
    return result


async def research_critique_node(state: AgentState) -> dict:
    result = await run_research_critique(state)
    critique = result.get("research_critique_result")
    score = critique.overall_score if critique else 0.7
    result["critic_score"] = score
    result["verdict"] = critique.verdict if critique else "REVISE"
    result["revision_count"] = state.get("revision_count", 0) + 1
    if critique and critique.follow_up_queries:
        result["unresolved_questions"] = list(state.get("unresolved_questions", []) or []) + critique.follow_up_queries
    return result


async def qa_node(state: AgentState) -> dict:
    result = await run_qa(state)
    qa = result.get("qa_result")
    if qa:
        result["verdict"] = qa.verdict.value
    else:
        result["verdict"] = "REVISE"
    result["qa_iterations"] = state.get("qa_iterations", 0) + 1
    result["iteration"] = state.get("iteration", 1) + 1
    return result


async def save_to_knowledge_library(state: AgentState) -> dict:
    from backend.knowledge_library.facts_store import facts_store
    from backend.knowledge_library.ragflow_client import ragflow
    from backend.knowledge_library.sources_store import sources_store

    session_id: str = state.get("session_id", state.get("report_id", str(uuid.uuid4())))
    results = state.get("research_results", [])
    citation_verification = state.get("citation_verification")
    intake = state.get("intake_result")
    topic_tags: list[str] = list(intake.key_entities) if intake else []

    if citation_verification and results:
        await facts_store.save_verified_facts(
            results, citation_verification, session_id, topic_tags
        )

    all_sources = [s for r in results for s in r.sources]
    if all_sources:
        await sources_store.upsert_sources(all_sources, topic_tags)

    paths: list[str] = []
    report = state.get("report")
    if report:
        out_dir = settings.outputs_dir
        os.makedirs(out_dir, exist_ok=True)
        fname = f"{session_id}.json"
        report_path = os.path.join(out_dir, fname)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
        paths.append(report_path)
        logger.info(f"Report saved to {report_path}")

        try:
            await ragflow.save_report(
                report,
                session_id,
                {
                    "session_id": session_id,
                    "qa_verdict": state.get("verdict", ""),
                    "status": state.get("status", ""),
                    "topic_tags": topic_tags,
                },
            )
        except Exception as exc:
            logger.warning(f"RAGFlow report save failed: {exc}")

    try:
        verified_units = await facts_store.get_by_session(session_id)
        if verified_units:
            await ragflow.save_facts(verified_units)
    except Exception as exc:
        logger.warning(f"RAGFlow facts save failed: {exc}")

    logger.info(
        f"Knowledge library saved: {sum(len(r.findings) for r in results)} findings, "
        f"{len(all_sources)} sources, session={session_id}"
    )
    all_paths = list(state.get("final_report_paths") or []) + paths
    return {
        "final_report_paths": all_paths,
        "current_agent": "save_to_knowledge_library",
        "status": "completed" if state.get("verdict") == "PASS" else "failed",
    }


def critique_decision(state: AgentState) -> str:
    score = state.get("critic_score", 1.0)
    rev = state.get("revision_count", 0)
    if score < 0.7 and rev < 3:
        logger.info(f"Critique REVISE (score={score:.2f}, revision={rev})")
        return "revise"
    logger.info(f"Critique PROCEED (score={score:.2f}, revision={rev})")
    return "proceed"


def qa_decision(state: AgentState) -> str:
    qa_iterations = state.get("qa_iterations", 0)
    verdict = state.get("verdict", "PASS")
    iteration = state.get("iteration", 1)
    max_iter = state.get("max_iterations", 3)

    if verdict == "PASS":
        logger.info(f"QA -> save (PASS, iter={iteration})")
        return "pass"

    if verdict == "REJECT":
        if qa_iterations >= 3 or iteration >= max_iter:
            logger.info(
                f"QA -> fail (REJECT persisted, qa_iterations={qa_iterations}, iter={iteration}, max_iter={max_iter})"
            )
            return "fail"
        logger.info(f"QA -> REJECT -> back to supervisor/research (iter={iteration})")
        return "reject"

    if qa_iterations >= 3 or iteration >= max_iter:
        logger.info(
            f"QA -> fail (REVISE persisted, qa_iterations={qa_iterations}, iter={iteration}, max_iter={max_iter})"
        )
        return "fail"

    logger.info(f"QA -> REVISE -> back to renderer (iter={iteration})")
    return "revise"


def build_graph(checkpointer: Any = None) -> Any:
    wf = StateGraph(AgentState)

    wf.add_node("intake", run_intake)
    wf.add_node("cost_guard_post_intake", cost_guard_post_intake)
    wf.add_node("prompt_router", run_prompt_router)
    wf.add_node("prompt_king", run_prompt_king)
    wf.add_node("prompt_splitter", run_prompt_splitter)
    wf.add_node("supervisor", run_supervisor)
    wf.add_node("research", run_research)
    wf.add_node("cost_guard_post_research", cost_guard_post_research)
    wf.add_node("summarization", run_summarization)
    wf.add_node("reflect", run_reflect)
    wf.add_node("citation_verifier", run_citation_verifier)
    wf.add_node("research_critique", research_critique_node)
    wf.add_node("viz_agent", run_viz_agent)
    wf.add_node("render_and_present", render_and_present)
    wf.add_node("qa", qa_node)
    wf.add_node("save_to_knowledge_library", save_to_knowledge_library)

    wf.set_entry_point("intake")
    wf.add_edge("intake", "cost_guard_post_intake")
    wf.add_edge("cost_guard_post_intake", "prompt_router")
    wf.add_edge("prompt_router", "prompt_king")
    wf.add_edge("prompt_king", "prompt_splitter")
    wf.add_edge("prompt_splitter", "supervisor")
    wf.add_edge("supervisor", "research")
    wf.add_edge("research", "cost_guard_post_research")
    wf.add_edge("cost_guard_post_research", "summarization")
    wf.add_edge("summarization", "reflect")
    wf.add_edge("reflect", "citation_verifier")
    wf.add_edge("citation_verifier", "research_critique")

    wf.add_conditional_edges(
        "research_critique",
        critique_decision,
        {"revise": "supervisor", "proceed": "viz_agent"},
    )

    wf.add_edge("viz_agent", "render_and_present")
    wf.add_edge("render_and_present", "qa")

    wf.add_conditional_edges(
        "qa",
        qa_decision,
        {
            "pass": "save_to_knowledge_library",
            "revise": "render_and_present",
            "reject": "supervisor",
            "fail": "save_to_knowledge_library",
        },
    )

    wf.add_edge("save_to_knowledge_library", END)

    logger.info("LangGraph pipeline built (16 nodes)")
    return wf.compile(checkpointer=checkpointer)


@asynccontextmanager
async def pipeline_context() -> AsyncIterator[tuple[Any, Any]]:
    postgres_cm = None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        postgres_cm = AsyncPostgresSaver.from_conn_string(
            normalize_database_url(settings.postgres_url, async_driver=None)
        )
    except Exception as e:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        logger.warning(f"Postgres unavailable ({e}), using MemorySaver fallback")
        yield build_graph(checkpointer=checkpointer), checkpointer
        return

    async with postgres_cm as checkpointer:
        try:
            await checkpointer.setup()
        except Exception as e:
            from langgraph.checkpoint.memory import MemorySaver

            fallback = MemorySaver()
            logger.warning(f"Postgres unavailable ({e}), using MemorySaver fallback")
            yield build_graph(checkpointer=fallback), fallback
            return

        logger.info("Pipeline ready with PostgresSaver checkpointer")
        yield build_graph(checkpointer=checkpointer), checkpointer
