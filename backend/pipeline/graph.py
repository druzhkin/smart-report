from __future__ import annotations

import asyncio
import json
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
from backend.agents.synthesis_agent import run_synthesis_gate
from backend.agents.viz_agent import run_viz_agent
from backend.config import normalize_database_url, settings
from backend.pipeline.cost_guard import BudgetExceededError, InsufficientEvidenceError
from backend.pipeline.state import AgentState
from backend.schemas.master_prompt import MasterPrompt, ReportSchema, SectionSchema


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


def _fallback_master_prompt(state: AgentState, reason: str) -> MasterPrompt:
    intake = state.get("intake_result")
    language = getattr(intake, "language", "en") if intake else "en"
    cleaned_query = getattr(intake, "cleaned_query", state.get("original_request", "")) if intake else state.get("original_request", "")
    entities = getattr(intake, "key_entities", []) if intake else []
    domain = getattr(intake, "domain", "general") if intake else "general"

    if language == "ru":
        sections = [
            SectionSchema(title="Ключевые выводы", required=True),
            SectionSchema(title="Анализ и контекст", required=True),
            SectionSchema(title="Практические рекомендации", required=True),
        ]
        system_prompt = "Ты аналитик. Пиши структурированный отчёт только по подтверждённым фактам."
        reliability_line = "Явно отмечай неопределённость и не выдумывай факты."
    else:
        sections = [
            SectionSchema(title="Key Findings", required=True),
            SectionSchema(title="Analysis and Context", required=True),
            SectionSchema(title="Practical Recommendations", required=True),
        ]
        system_prompt = "You are an analyst. Write a structured report grounded in verifiable evidence."
        reliability_line = "State uncertainty explicitly and avoid unsupported claims."

    master_prompt_text = (
        "## PROFILE\n"
        "Senior research analyst\n\n"
        "## KNOWLEDGE\n"
        f"Domain: {domain}. Entities: {', '.join(entities) if entities else 'n/a'}.\n"
        f"Query: {cleaned_query}\n\n"
        "## REASONING\n"
        "Decompose the problem into evidence-backed sub-questions and synthesize tradeoffs.\n\n"
        "## RELIABILITY\n"
        f"{reliability_line} Fallback activated because Prompt King failed: {reason}"
    )

    return MasterPrompt(
        system_prompt=system_prompt,
        user_prompt=cleaned_query,
        master_prompt=master_prompt_text,
        report_schema=ReportSchema(sections=sections),
        target_model="anthropic/claude-sonnet-4",
        temperature=0.3,
    )


async def prompt_king_node(state: AgentState) -> dict:
    try:
        return await run_prompt_king(state)
    except Exception as exc:
        logger.error(f"Prompt King failed, using fallback master prompt: {exc}")
        fallback = _fallback_master_prompt(state, str(exc))
        return {
            "master_prompt": fallback,
            "messages": state.get("messages", []) + [
                {
                    "role": "prompt_king",
                    "content": json.dumps(
                        {
                            "warning": "prompt_king_fallback",
                            "reason": str(exc),
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
            "current_agent": "prompt_king",
        }


async def _run_with_deadline(coro, *, seconds: int, label: str) -> dict:
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"{label} timed out after {seconds}s") from exc


async def prompt_router_node(state: AgentState) -> dict:
    return await _run_with_deadline(
        run_prompt_router(state),
        seconds=120,
        label="prompt_router",
    )


async def supervisor_node(state: AgentState) -> dict:
    return await _run_with_deadline(
        run_supervisor(state),
        seconds=180,
        label="supervisor",
    )


async def research_node(state: AgentState) -> dict:
    return await _run_with_deadline(
        run_research(state),
        seconds=420,
        label="research",
    )


async def summarization_node(state: AgentState) -> dict:
    return await _run_with_deadline(
        run_summarization(state),
        seconds=240,
        label="summarization",
    )


async def reflect_node(state: AgentState) -> dict:
    return await _run_with_deadline(
        run_reflect(state),
        seconds=240,
        label="reflect",
    )


async def citation_verifier_node(state: AgentState) -> dict:
    return await _run_with_deadline(
        run_citation_verifier(state),
        seconds=300,
        label="citation_verifier",
    )


async def viz_node(state: AgentState) -> dict:
    return await _run_with_deadline(
        run_viz_agent(state),
        seconds=180,
        label="viz_agent",
    )


async def qa_node_with_deadline(state: AgentState) -> dict:
    result = await _run_with_deadline(
        run_qa(state),
        seconds=240,
        label="qa",
    )
    qa = result.get("qa_result")
    if qa:
        result["verdict"] = qa.verdict.value
    else:
        result["verdict"] = "REVISE"
    result["qa_iterations"] = state.get("qa_iterations", 0) + 1
    result["iteration"] = state.get("iteration", 1) + 1
    return result


async def render_and_present(state: AgentState) -> dict:
    base_cost = state.get("cost_usd", 0.0)

    render_res = await _run_with_deadline(
        run_renderer(state),
        seconds=420,
        label="renderer",
    )
    r_cost = render_res.get("cost_usd", base_cost) - base_cost

    pres_state = dict(state)
    pres_state["report"] = render_res.get("report")
    pres_state["chart_paths"] = state.get("chart_paths", [])
    pres_res = await _run_with_deadline(
        run_presentation(pres_state),
        seconds=180,
        label="presentation",
    )
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
    result = await _run_with_deadline(
        run_research_critique(state),
        seconds=240,
        label="research_critique",
    )
    critique = result.get("research_critique_result")
    score = critique.overall_score if critique else 0.7
    result["critic_score"] = score
    result["verdict"] = critique.verdict if critique else "REVISE"
    result["revision_count"] = state.get("revision_count", 0) + 1
    if critique and critique.follow_up_queries:
        result["unresolved_questions"] = list(state.get("unresolved_questions", []) or []) + critique.follow_up_queries
    return result


async def qa_node(state: AgentState) -> dict:
    return await qa_node_with_deadline(state)


async def save_to_knowledge_library(state: AgentState) -> dict:
    from backend.knowledge_library.facts_store import facts_store
    from backend.knowledge_library.ragflow_client import ragflow
    from backend.knowledge_library.sources_store import sources_store

    async def _await_with_timeout(coro, timeout_seconds: float, op_name: str, default: Any = None) -> Any:
        try:
            return await asyncio.wait_for(coro, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning(f"{op_name} timed out after {timeout_seconds:.0f}s; continuing without blocking report delivery")
            return default
        except Exception as exc:
            logger.warning(f"{op_name} failed: {exc}")
            return default

    session_id: str = state.get("session_id", state.get("report_id", str(uuid.uuid4())))
    results = state.get("research_results", [])
    citation_verification = state.get("citation_verification")
    intake = state.get("intake_result")
    topic_tags: list[str] = list(intake.key_entities) if intake else []

    if citation_verification and results:
        await _await_with_timeout(
            facts_store.save_verified_facts(results, citation_verification, session_id, topic_tags),
            timeout_seconds=20,
            op_name="facts_store.save_verified_facts",
            default=0,
        )

    all_sources = [s for r in results for s in r.sources]
    if all_sources:
        await _await_with_timeout(
            sources_store.upsert_sources(all_sources, topic_tags),
            timeout_seconds=20,
            op_name="sources_store.upsert_sources",
        )

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

        await _await_with_timeout(
            ragflow.save_report(
                report,
                session_id,
                {
                    "session_id": session_id,
                    "qa_verdict": state.get("verdict", ""),
                    "status": state.get("status", ""),
                    "topic_tags": topic_tags,
                },
            ),
            timeout_seconds=45,
            op_name="ragflow.save_report",
            default="",
        )

    verified_units = await _await_with_timeout(
        facts_store.get_by_session(session_id),
        timeout_seconds=10,
        op_name="facts_store.get_by_session",
        default=[],
    )
    if verified_units:
        max_facts_sync = 50
        if len(verified_units) > max_facts_sync:
            logger.warning(
                f"RAGFlow facts sync capped at {max_facts_sync} (session={session_id}, total={len(verified_units)})"
            )
        await _await_with_timeout(
            ragflow.save_facts(verified_units[:max_facts_sync]),
            timeout_seconds=180,
            op_name="ragflow.save_facts",
        )

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
    max_revisions = state.get("max_iterations", 3)
    budget = _get_budget(state)
    cost = state.get("cost_usd", 0.0)
    remaining_budget = max(0.0, budget - cost)
    total_sources = sum(len(result.sources) for result in list(state.get("research_results", []) or []))
    citation = state.get("citation_verification")
    citation_failed = bool(citation and not citation.passed)
    critique = state.get("research_critique_result")
    blocking_issues = len(critique.blocking_issues) if critique else 0

    min_budget_for_revision = max(0.35, budget * 0.18)
    can_revise = rev < max_revisions and remaining_budget >= min_budget_for_revision
    quality_is_low = score < 0.7
    severe_quality_risk = citation_failed or blocking_issues >= 2 or score < 0.5

    if severe_quality_risk and can_revise:
        logger.info(
            "Critique REVISE due to severe quality risk "
            f"(score={score:.2f}, revision={rev}, blocking={blocking_issues}, "
            f"citation_failed={citation_failed}, remaining=${remaining_budget:.4f})"
        )
        return "revise"

    if severe_quality_risk and not can_revise:
        logger.warning(
            "Critique ABORT due to severe quality risk with no safe revision budget "
            f"(score={score:.2f}, revision={rev}/{max_revisions}, blocking={blocking_issues}, "
            f"citation_failed={citation_failed}, remaining=${remaining_budget:.4f}, sources={total_sources})"
        )
        return "abort"

    if quality_is_low and can_revise:
        logger.info(
            "Critique REVISE "
            f"(score={score:.2f}, revision={rev}, remaining=${remaining_budget:.4f})"
        )
        return "revise"

    if quality_is_low and not can_revise:
        logger.warning(
            "Critique ABORT due to low score with no safe revision budget "
            f"(score={score:.2f}, revision={rev}/{max_revisions}, remaining=${remaining_budget:.4f})"
        )
        return "abort"

    logger.info(f"Critique PROCEED (score={score:.2f}, revision={rev})")
    return "proceed"


def synthesis_decision(state: AgentState) -> str:
    ready = bool(state.get("synthesis_ready"))
    if ready:
        logger.info("Synthesis gate PROCEED")
        return "proceed"

    rev = state.get("revision_count", 0)
    max_revisions = state.get("max_iterations", 3)
    budget = _get_budget(state)
    cost = state.get("cost_usd", 0.0)
    remaining_budget = max(0.0, budget - cost)
    min_budget_for_revision = max(0.35, budget * 0.18)
    can_revise = rev < max_revisions and remaining_budget >= min_budget_for_revision
    blocking = list((state.get("synthesis_payload") or {}).get("blocking_reasons") or [])

    if can_revise:
        logger.warning(
            "Synthesis gate REVISE "
            f"(revision={rev}/{max_revisions}, remaining=${remaining_budget:.4f}, "
            f"blockers={blocking[:2]})"
        )
        return "revise"

    logger.warning(
        "Synthesis gate ABORT "
        f"(revision={rev}/{max_revisions}, remaining=${remaining_budget:.4f}, "
        f"blockers={blocking[:2]})"
    )
    return "abort"


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
    wf.add_node("prompt_router", prompt_router_node)
    wf.add_node("prompt_king", prompt_king_node)
    wf.add_node("prompt_splitter", run_prompt_splitter)
    wf.add_node("supervisor", supervisor_node)
    wf.add_node("research", research_node)
    wf.add_node("cost_guard_post_research", cost_guard_post_research)
    wf.add_node("summarization", summarization_node)
    wf.add_node("reflect", reflect_node)
    wf.add_node("citation_verifier", citation_verifier_node)
    wf.add_node("research_critique", research_critique_node)
    wf.add_node("synthesis_gate", run_synthesis_gate)
    wf.add_node("viz_agent", viz_node)
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
        {"revise": "supervisor", "proceed": "synthesis_gate", "abort": "save_to_knowledge_library"},
    )

    wf.add_conditional_edges(
        "synthesis_gate",
        synthesis_decision,
        {"revise": "supervisor", "proceed": "viz_agent", "abort": "save_to_knowledge_library"},
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

    logger.info("LangGraph pipeline built (17 nodes)")
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
