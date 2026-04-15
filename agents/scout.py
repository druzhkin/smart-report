"""Scout — one ScoutTask → raw search → Finding list."""
from __future__ import annotations

import json

from config import load_prompt, model_for, settings
from llm import call_json
from models import Finding, ScoutResult, ScoutTask
from pydantic import BaseModel
from search import search

SYSTEM = load_prompt("scout")


class _ScoutPayload(BaseModel):
    findings: list[Finding]
    notes: str | None = None


async def scout(task: ScoutTask) -> ScoutResult:
    raw = await search(task.query_focus, focus=task.cell)
    citations_blob = json.dumps(raw.get("citations", []), ensure_ascii=False, indent=2)
    user = (
        f"Ячейка: {task.cell}\n"
        f"Задание: {task.query_focus}\n"
        f"Подсказки по источникам: {task.source_hints}\n\n"
        f"--- Сырой результат поиска ---\n{raw.get('text', '')}\n\n"
        f"--- Цитаты / URL ---\n{citations_blob}\n\n"
        "Извлеки находки по контракту из system prompt. Только JSON."
    )
    payload = await call_json(
        model=model_for("scout"),
        system=SYSTEM,
        user=user,
        schema=_ScoutPayload,
        temperature=0.2,
    )
    return ScoutResult(task=task, findings=payload.findings, notes=payload.notes)
