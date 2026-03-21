"""Shared JSON parsing utilities for LLM responses."""
from __future__ import annotations

import json
import re

from loguru import logger

_DECODER = json.JSONDecoder()


def _try_raw_decode(text: str) -> dict | None:
    """Find and parse the first valid JSON object, ignoring trailing content."""
    # Find the first '{' and attempt raw_decode from each position
    for i, ch in enumerate(text):
        if ch == '{':
            try:
                obj, _ = _DECODER.raw_decode(text, i)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def parse_llm_json(raw: str, context: str = "") -> dict:
    """Parse JSON from LLM output, handling markdown fences and preamble/trailing text.

    Raises ValueError if no valid JSON object can be extracted.
    """
    clean = raw.strip()

    # Strip markdown code fences
    if clean.startswith("```"):
        clean = re.sub(r'^```(?:json)?\n?', '', clean)
        clean = re.sub(r'\n?```$', '', clean)
    clean = clean.strip()

    # Fast path: well-formed JSON
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Robust fallback: scan for first valid JSON object (handles preamble + trailing text)
    result = _try_raw_decode(clean)
    if result is not None:
        return result

    label = f"[{context}] " if context else ""
    logger.error(f"{label}JSON parse failed. Raw: {raw[:500]}")
    raise ValueError(f"{label}JSON parse failed. Raw: {raw[:200]}")


def supports_json_mode(model: str) -> bool:
    """Return True if the model supports response_format: json_object via OpenRouter."""
    return model.startswith("openai/") or model.startswith("google/")
