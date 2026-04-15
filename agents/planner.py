"""Planner — goal → Matrix. Plus helpers for --deepen and --add-domain."""
from __future__ import annotations

from config import load_prompt, settings
from llm import call_json
from models import CellPlan, Domain, Matrix, ScoutTask
from pydantic import BaseModel

SYSTEM = load_prompt("planner")
DEEPENER_SYSTEM = load_prompt("deepener")
EXPANDER_SYSTEM = load_prompt("domain_expander")


class _DeepenerPayload(BaseModel):
    tasks: list[ScoutTask]


class _ExpanderPayload(BaseModel):
    domain: Domain
    cell_plans: list[CellPlan]


async def planner(goal: str) -> Matrix:
    user = (
        f"Цель пользователя:\n\n{goal}\n\n"
        "Построй матрицу и поисковые задания по правилам из system prompt. Только JSON."
    )
    matrix = await call_json(
        model=settings.planner_model,
        system=SYSTEM,
        user=user,
        schema=Matrix,
        temperature=0.4,
    )
    if not matrix.goal:
        matrix = matrix.model_copy(update={"goal": goal})
    expected = {f"{d.name} / {l.name}" for d in matrix.domains for l in d.layers}
    matrix.cell_plans = [cp for cp in matrix.cell_plans if cp.cell in expected]
    have = {cp.cell for cp in matrix.cell_plans}
    for cell in expected - have:
        matrix.cell_plans.append(CellPlan(cell=cell, tasks=[]))
    return matrix


async def plan_deepen(
    cell: str,
    focus: str,
    existing_gaps: list[str] | None = None,
    existing_entities: list[str] | None = None,
) -> list[ScoutTask]:
    """Generate 3–5 new ScoutTasks for a specific cell + focus."""
    user = (
        f"Ячейка: {cell}\n"
        f"Фокус углубления: {focus}\n"
        f"Уже известные пробелы блока: {existing_gaps or []}\n"
        f"Ключевые сущности блока: {existing_entities or []}\n\n"
        "Верни 3–5 новых заданий, которые бьют в указанный фокус и не дублируют уже известное. Только JSON."
    )
    payload = await call_json(
        model=settings.planner_model,
        system=DEEPENER_SYSTEM,
        user=user,
        schema=_DeepenerPayload,
        temperature=0.35,
    )
    for t in payload.tasks:
        if not t.cell:
            t = t.model_copy(update={"cell": cell})
    return [t.model_copy(update={"cell": cell}) for t in payload.tasks]


async def plan_new_domain(
    goal: str,
    existing_matrix: Matrix,
    domain_name: str,
    layers_hint: list[str] | None = None,
) -> tuple[Domain, list[CellPlan]]:
    """Produce a new Domain + its cell_plans, without duplicating existing cells."""
    existing = [
        {"name": d.name, "layers": [l.name for l in d.layers]} for d in existing_matrix.domains
    ]
    user = (
        f"Цель отчёта: {goal}\n"
        f"Существующие домены: {existing}\n"
        f"Новый домен: {domain_name}\n"
        f"Предложенные слои (опционально): {layers_hint or []}\n\n"
        "Построй новый Domain (2–4 слоя) и cell_plans для его ячеек. Только JSON."
    )
    payload = await call_json(
        model=settings.planner_model,
        system=EXPANDER_SYSTEM,
        user=user,
        schema=_ExpanderPayload,
        temperature=0.4,
    )
    expected = {f"{payload.domain.name} / {l.name}" for l in payload.domain.layers}
    payload.cell_plans = [cp for cp in payload.cell_plans if cp.cell in expected]
    have = {cp.cell for cp in payload.cell_plans}
    for cell in expected - have:
        payload.cell_plans.append(CellPlan(cell=cell, tasks=[]))
    return payload.domain, payload.cell_plans
