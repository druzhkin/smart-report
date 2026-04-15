"""Causal chains — Report → long cross-domain causal chains (4+ links)."""
from __future__ import annotations

import json

from config import load_prompt, model_for
from llm import call_json
from models import Block, CausalChain, Connection
from pydantic import BaseModel

SYSTEM = load_prompt("causal_chains")


class _ChainsPayload(BaseModel):
    causal_chains: list[CausalChain]


async def causal_chains(
    goal: str,
    blocks: list[Block],
    connections: list[Connection],
) -> list[CausalChain]:
    blocks_compact = [
        {
            "cell": b.cell,
            "one_liner_excerpt": (b.summary or "")[:600],
            "key_entities": b.key_entities,
        }
        for b in blocks
    ]
    connections_compact = [
        {
            "domains": c.domains,
            "shared": c.shared_entity,
            "nature": c.nature,
            "description": c.description,
            "anchors": c.anchors,
        }
        for c in connections
    ]
    user = (
        f"Цель: {goal}\n\n"
        f"Блоки:\n{json.dumps(blocks_compact, ensure_ascii=False, indent=2)}\n\n"
        f"Связи:\n{json.dumps(connections_compact, ensure_ascii=False, indent=2)}\n\n"
        "Собери 2–4 длинных причинных цепочки (минимум 4 звена каждая, пересекающих ≥2 домена). Только JSON."
    )
    payload = await call_json(
        model=model_for("analyst"),
        system=SYSTEM,
        user=user,
        schema=_ChainsPayload,
        temperature=0.4,
    )
    return payload.causal_chains
