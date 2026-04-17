"""Intake dialog agent — asks clarifying questions and proposes a research tier."""
from __future__ import annotations

import json
import logging

from config import load_prompt, settings
from llm import call_text
from models import IntakeMessage

log = logging.getLogger("agents.intake")

_SYSTEM = load_prompt("intake_dialog")


def _build_user_message(goal: str, history: list[IntakeMessage], force_proposal: bool) -> str:
    parts = [f"Цель исследования: {goal}"]
    if history:
        parts.append("\nИстория диалога:")
        for msg in history:
            role_label = "Консультант" if msg.role == "assistant" else "Пользователь"
            parts.append(f"{role_label}: {msg.content}")
    if force_proposal:
        parts.append(
            "\n[СИСТЕМНАЯ ИНСТРУКЦИЯ: достаточно информации для пропозала. "
            "Верни JSON с mode=proposal прямо сейчас.]"
        )
    return "\n".join(parts)


async def intake_turn(goal: str, history: list[IntakeMessage]) -> dict:
    """Run one turn of the intake dialog.

    Returns a dict with either:
      {"mode": "question", "question": str}
    or
      {"mode": "proposal", "tier": str, "rationale": str, "enriched_goal": str}
    """
    # Count how many user answers we already have.
    user_turns = sum(1 for m in history if m.role == "user")
    force_proposal = user_turns >= settings.intake_max_turns

    user_msg = _build_user_message(goal, history, force_proposal)

    raw = await call_text(
        model=settings.intake_model,
        system=_SYSTEM,
        user=user_msg,
        temperature=0.4,
        max_tokens=1000,
    )

    # Strip markdown fences if the model adds them anyway.
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first and last fence lines
        inner = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(inner).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON object from surrounding prose.
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
        else:
            log.warning("intake_turn: could not parse JSON from model output, forcing proposal")
            data = {
                "mode": "proposal",
                "tier": "investment_brief",
                "rationale": "Не удалось структурировать диалог, предлагаем стандартный формат.",
                "enriched_goal": goal,
            }

    mode = data.get("mode")
    if mode not in ("question", "proposal"):
        log.warning("intake_turn: unexpected mode=%r, treating as proposal", mode)
        data["mode"] = "proposal"
        data.setdefault("tier", "investment_brief")
        data.setdefault("rationale", "")
        data.setdefault("enriched_goal", goal)

    return data
