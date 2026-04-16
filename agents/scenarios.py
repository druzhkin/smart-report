"""Scenarios agent — builds a Cone of Plausibility for predictive questions."""
from __future__ import annotations

import json

from config import load_prompt
from llm import call_json
from models import Block, Connection, ScenarioCone
from pydantic import BaseModel

SYSTEM = load_prompt("scenarios")


class _ScenarioConePayload(BaseModel):
    scenario_cone: ScenarioCone


async def scenarios(
    goal: str,
    question_type: str,
    blocks: list[Block],
    connections: list[Connection],
) -> ScenarioCone | None:
    """Return a ScenarioCone for predictive questions, None otherwise."""
    if question_type != "predictive":
        return None

    blocks_compact = [
        {
            "cell": b.cell,
            "summary_excerpt": (b.summary or "")[:1000],
            "key_entities": b.key_entities,
            "strong_findings": [
                {
                    "claim": f.claim,
                    "source_label": f.source_label,
                    "numeric_values": f.numeric_values,
                }
                for f in b.findings
                if f.has_numbers
            ][:5],
            "indicators": [
                {
                    "hypothesis": iw.hypothesis,
                    "indicator": iw.indicator,
                    "timeframe": iw.timeframe,
                }
                for iw in (b.indicators or [])
            ],
        }
        for b in blocks
    ]
    connections_compact = [
        {
            "domains": c.domains,
            "nature": c.nature,
            "description": c.description,
            "novelty": c.novelty,
        }
        for c in connections
    ]
    user = (
        f"Цель исследования (предсказательный вопрос): {goal}\n\n"
        f"Блоки:\n{json.dumps(blocks_compact, ensure_ascii=False, indent=2)}\n\n"
        f"Связи:\n{json.dumps(connections_compact, ensure_ascii=False, indent=2)}\n\n"
        "Построй Конус правдоподобных будущих по контракту ScenarioCone. "
        "Верни JSON с единственным ключом scenario_cone."
    )
    payload = await call_json(
        model="google/gemini-3-flash-preview",
        system=SYSTEM,
        user=user,
        schema=_ScenarioConePayload,
        temperature=0.5,
    )
    return payload.scenario_cone
