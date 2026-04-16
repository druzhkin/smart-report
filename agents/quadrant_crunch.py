"""Quadrant Crunch — CIA SAT assumption inversion for each block."""
from __future__ import annotations

import asyncio
import json

from config import load_prompt, model_for
from llm import call_json
from models import Block, BlockInversions
from pydantic import BaseModel

SYSTEM = load_prompt("quadrant_crunch")


class _BlockInversionsPayload(BaseModel):
    block_cell: str
    inversions: list[dict]
    unfalsifiable_flag: bool = False


async def _crunch_block(goal: str, block: Block) -> BlockInversions:
    """Invert load-bearing assumptions for a single block."""
    block_data = {
        "cell": block.cell,
        "summary_excerpt": (block.summary or "")[:1000],
        "assumptions": block.assumptions,
        "key_entities": block.key_entities,
    }
    user = (
        f"Цель исследования: {goal}\n\n"
        f"Блок:\n{json.dumps(block_data, ensure_ascii=False, indent=2)}\n\n"
        "Сгенерируй инверсии для 2–3 наиболее несущих допущений. "
        "Верни JSON с полями block_cell, inversions, unfalsifiable_flag."
    )
    payload = await call_json(
        model=model_for("analyst"),
        system=SYSTEM,
        user=user,
        schema=_BlockInversionsPayload,
        temperature=0.4,
    )
    # Re-validate via BlockInversions to enforce nested schema
    return BlockInversions(
        block_cell=payload.block_cell,
        inversions=payload.inversions,  # type: ignore[arg-type]
        unfalsifiable_flag=payload.unfalsifiable_flag,
    )


async def quadrant_crunch(
    goal: str,
    blocks: list[Block],
) -> list[BlockInversions]:
    """Return BlockInversions for every block that has assumptions."""
    targets = [b for b in blocks if b.assumptions]
    if not targets:
        return []
    tasks = [_crunch_block(goal, b) for b in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[BlockInversions] = []
    for r in results:
        if isinstance(r, BlockInversions):
            out.append(r)
    return out
