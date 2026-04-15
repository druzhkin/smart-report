"""Bisociator — blocks → cross-domain Connections. Expanded input."""
from __future__ import annotations

import json

from config import load_prompt, model_for, settings
from llm import call_json
from models import Block, Connection
from pydantic import BaseModel

SYSTEM = load_prompt("bisociator")


class _BisociatorPayload(BaseModel):
    connections: list[Connection]


def _condense_block(b: Block) -> dict:
    return {
        "cell": b.cell,
        "summary_excerpt": b.summary[:2500],
        "key_numbers": [f.claim for f in b.findings if f.has_numbers][:8],
        "key_findings": [
            {"claim": f.claim, "source": f.source, "type": f.source_type}
            for f in b.findings
        ][:10],
        "key_entities": b.key_entities,
        "assumptions": b.assumptions,
        "gaps": b.gaps,
    }


async def bisociator(blocks: list[Block], *, min_target: int = 10) -> list[Connection]:
    condensed = [_condense_block(b) for b in blocks]
    user = (
        f"Блоки отчёта (расширенный контекст):\n"
        f"{json.dumps(condensed, ensure_ascii=False, indent=2)}\n\n"
        f"Цель: найти минимум {min_target} связей четырёх типов "
        "(paradox / shared_variable / causal_chain / unexpected_confirmation). "
        "Для каждой связи обязательно: anchors — цитаты из блоков, и novelty — что нового даёт связь. "
        "Только JSON."
    )
    payload = await call_json(
        model=model_for("bisociator"),
        system=SYSTEM,
        user=user,
        schema=_BisociatorPayload,
        temperature=0.55,
    )
    return payload.connections


async def bisociate_pair(block_a: Block, block_b: Block) -> list[Connection]:
    """Focused connect for exactly two blocks (used by CLI --connect)."""
    user = (
        "Два блока из одного отчёта. Найди все возможные связи (paradox / shared_variable / "
        "causal_chain / unexpected_confirmation) между ними. Не ограничивайся одной-двумя — "
        "разверни максимально. Для каждой связи — anchors и novelty. Только JSON.\n\n"
        f"{json.dumps([_condense_block(block_a), _condense_block(block_b)], ensure_ascii=False, indent=2)}"
    )
    payload = await call_json(
        model=model_for("bisociator"),
        system=SYSTEM,
        user=user,
        schema=_BisociatorPayload,
        temperature=0.55,
    )
    return payload.connections
