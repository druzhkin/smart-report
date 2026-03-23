from __future__ import annotations

import json
import re

from loguru import logger

from backend.pipeline.state import AgentState
from backend.schemas.research_result import (
    ResearchHypothesis,
    ResearchTask,
    TaskDecomposition,
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "task"


def _infer_hypotheses(query: str) -> list[ResearchHypothesis]:
    hypotheses: list[ResearchHypothesis] = []
    text = query.lower()
    if "market" in text or "рын" in text:
        hypotheses.append(
            ResearchHypothesis(
                id="market-growth",
                statement="The target market is growing fast enough to justify deeper investigation.",
            )
        )
    if "compet" in text or "конкур" in text:
        hypotheses.append(
            ResearchHypothesis(
                id="fragmented-competition",
                statement="The competitive landscape is fragmented enough to create a defendable entry angle.",
            )
        )
    if "invest" in text or "инвест" in text:
        hypotheses.append(
            ResearchHypothesis(
                id="investment-case",
                statement="The topic supports a viable investment or strategic allocation case.",
            )
        )
    return hypotheses


def _build_fallback_decomposition(state: AgentState) -> TaskDecomposition:
    intake = state.get("intake_result")
    master = state.get("master_prompt")
    query = (
        master.user_prompt
        if master and master.user_prompt
        else state.get("user_request", {}).get("query", state.get("original_request", ""))
    )

    section_titles = []
    if master and master.report_schema and master.report_schema.sections:
        section_titles = [section.title for section in master.report_schema.sections if section.title]

    if not section_titles:
        section_titles = [
            "Market Overview",
            "Competitive Landscape",
            "Demand Drivers",
            "Risks and Constraints",
            "Strategic Implications",
        ]

    subquestions: list[ResearchTask] = []
    for idx, section_title in enumerate(section_titles[:6], start=1):
        task_id = _slugify(section_title)
        depends_on = [subquestions[0].id] if idx > 1 and "implication" in section_title.lower() else []
        subquestions.append(
            ResearchTask(
                id=task_id,
                question=f"{section_title}: {query}",
                depends_on=depends_on,
                priority=1 if idx <= 3 else 2,
                rationale=f"Cover the '{section_title}' angle before synthesis.",
                evidence_required=[section_title],
            )
        )

    ambiguities = list(getattr(intake, "clarifying_questions", []) or [])
    return TaskDecomposition(
        main_question=query,
        subquestions=subquestions,
        hypotheses=_infer_hypotheses(query),
        ambiguities=ambiguities,
    )


async def run_prompt_splitter(state: AgentState) -> dict:
    logger.info("Prompt Splitter agent started")
    master = state.get("master_prompt")
    if not master:
        logger.warning("No master prompt found, using original request for decomposition")

    decomposition = _build_fallback_decomposition(state)
    data_queries = [task.question for task in decomposition.subquestions] or [decomposition.main_question]

    logger.info(
        f"Prompt Splitter produced {len(decomposition.subquestions)} research tasks and "
        f"{len(decomposition.hypotheses)} hypotheses"
    )
    return {
        "task_decomposition": decomposition,
        "research_tasks": decomposition.subquestions,
        "hypotheses": decomposition.hypotheses,
        "unresolved_questions": decomposition.ambiguities,
        "data_queries": data_queries,
        "messages": state.get("messages", []) + [
            {"role": "prompt_splitter", "content": decomposition.model_dump_json()}
        ],
        "current_agent": "prompt_splitter",
    }
