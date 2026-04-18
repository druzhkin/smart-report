"""Bisociator: list[Block] -> list[CrossLink] (shared variables across domains)."""

from __future__ import annotations

import json
from pathlib import Path

from .io import load_prompt
from .llm import chat
from .models import Block, CrossLink

_VALID_TYPES = {"paradox", "causal_chain", "shared_mechanism", "unexpected_confirmation"}


async def bisociate(
    blocks: list[Block],
    *,
    mock: bool = False,
    log_dir: Path | None = None,
) -> list[CrossLink]:
    if not blocks:
        return []
    system = load_prompt("bisociator") or (
        "You are the Bisociator. Find cross-domain links between blocks where a shared "
        "variable creates a paradox, causal chain, shared mechanism, or unexpected confirmation. "
        "Return a JSON array of {cell_a, cell_b, shared_variable, type, insight, evidence_pointers}."
    )
    blocks_serialized = [b.model_dump() for b in blocks]
    user = (
        "Blocks (JSON):\n"
        f"{json.dumps(blocks_serialized, ensure_ascii=False, indent=2)}\n\n"
        "Return a JSON array."
    )
    raw = await chat(
        role="bisociator",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        mock=mock,
        log_dir=log_dir,
        # Note: not all providers accept json_object with a top-level array;
        # rely on strong prompt + fallback parser below.
    )
    items = _coerce_list(raw)
    out: list[CrossLink] = []
    for it in items:
        t = it.get("type")
        if t not in _VALID_TYPES:
            continue
        try:
            out.append(
                CrossLink(
                    cell_a=it["cell_a"],
                    cell_b=it["cell_b"],
                    shared_variable=it["shared_variable"],
                    type=t,
                    insight=it.get("insight", ""),
                    evidence_pointers=list(it.get("evidence_pointers", [])),
                )
            )
        except Exception:
            continue
    return out


def _coerce_list(raw: str) -> list[dict]:
    from .io import extract_json

    try:
        parsed = extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        # tolerate {"cross_links": [...]} or similar
        for v in parsed.values():
            if isinstance(v, list):
                return v
    return []
