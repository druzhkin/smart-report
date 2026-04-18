"""Planner: Question -> Matrix (domains x layers with ScoutTasks)."""

from __future__ import annotations

from pathlib import Path

from .io import extract_json, load_prompt
from .llm import chat
from .models import Cell, Matrix, Question, ScoutTask


async def plan(
    question: Question,
    *,
    mock: bool = False,
    log_dir: Path | None = None,
) -> Matrix:
    system = load_prompt("planner") or (
        "You are the Planner. Given a question, produce a JSON object with keys "
        "'domains' (list[str]) and 'cells' (list of {id, domain, layer, scout_task})."
    )
    user = (
        f"Question: {question.text}\n"
        f"question_id: {question.id}\n"
        "Return strict JSON: {\"domains\": [...], \"cells\": [...]}."
    )
    raw = await chat(
        role="planner",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        mock=mock,
        log_dir=log_dir,
        response_format={"type": "json_object"} if not mock else None,
    )
    data = extract_json(raw)

    cells: list[Cell] = []
    for c in data.get("cells", []):
        st = c.get("scout_task", {}) or {}
        cells.append(
            Cell(
                id=c["id"],
                domain=c["domain"],
                layer=c["layer"],
                scout_task=ScoutTask(
                    cell_id=st.get("cell_id", c["id"]),
                    query=st.get("query", ""),
                    target_sources=list(st.get("target_sources", [])),
                ),
            )
        )
    return Matrix(
        question_id=question.id,
        domains=list(data.get("domains", [])),
        cells=cells,
    )
