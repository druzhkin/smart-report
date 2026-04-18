"""Summarizer: (Report-in-progress) -> ExecutiveSummary. Runs after Bisociator."""

from __future__ import annotations

import json
from pathlib import Path

from .io import extract_json, load_prompt
from .llm import chat
from .models import Block, CrossLink, ExecutiveSummary, KeyTension, Question, TopNumber


async def summarize(
    question: Question,
    blocks: list[Block],
    cross_links: list[CrossLink],
    *,
    mock: bool = False,
    log_dir: Path | None = None,
) -> ExecutiveSummary:
    system = load_prompt("summarizer") or (
        "You are the Summarizer. Given a question, blocks, and cross-links, produce "
        "ExecutiveSummary with main_finding, top_numbers, key_tensions, open_questions."
    )
    user = (
        f"Question: {question.text}\n\n"
        "Blocks (JSON):\n"
        f"{json.dumps([b.model_dump() for b in blocks], ensure_ascii=False, indent=2)}\n\n"
        "Cross-links (JSON):\n"
        f"{json.dumps([c.model_dump() for c in cross_links], ensure_ascii=False, indent=2)}\n\n"
        "Return strict JSON per the contract in the system prompt."
    )
    raw = await chat(
        role="summarizer",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        mock=mock,
        log_dir=log_dir,
        response_format={"type": "json_object"} if not mock else None,
    )
    try:
        data = extract_json(raw)
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    top_numbers = [
        TopNumber(
            value=str(item.get("value", "")),
            context=str(item.get("context", "")),
            source_url=str(item.get("source_url", "")),
        )
        for item in (data.get("top_numbers") or [])
        if isinstance(item, dict) and item.get("value")
    ]
    key_tensions = [
        KeyTension(
            tension=str(item.get("tension", "")),
            pole_a=str(item.get("pole_a", "")),
            pole_b=str(item.get("pole_b", "")),
        )
        for item in (data.get("key_tensions") or [])
        if isinstance(item, dict) and item.get("tension")
    ]
    open_questions = [
        str(q) for q in (data.get("open_questions") or []) if q
    ]
    return ExecutiveSummary(
        main_finding=str(data.get("main_finding", "")),
        top_numbers=top_numbers,
        key_tensions=key_tensions,
        open_questions=open_questions,
    )
