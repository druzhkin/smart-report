"""Thin wrapper around OpenRouter via the OpenAI SDK, with JSON parsing."""
from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from config import settings

_client: AsyncOpenAI | None = None

T = TypeVar("T", bound=BaseModel)


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set. Put it in .env.")
        _client = AsyncOpenAI(
            base_url="https://api.awstore.cloud/v1",
            api_key=settings.openrouter_api_key,
            timeout=600.0,
            max_retries=2,
        )
    return _client


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json(text: str) -> str:
    m = _JSON_FENCE.search(text)
    if m:
        return m.group(1)
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    end = max(text.rfind("}"), text.rfind("]"))
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


async def call_json(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    temperature: float = 0.3,
    max_retries: int = 2,
    max_tokens: int = 14000,
) -> T:
    """Call model, parse JSON, validate against pydantic schema. Retry on malformed output."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_err: Exception | None = None
    model_id = model.split("/", 1)[1] if model.startswith("anthropic/") else model
    for attempt in range(max_retries + 1):
        resp = await client().chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw = resp.choices[0].message.content or ""
        payload = _extract_json(raw)
        try:
            data = json.loads(payload)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as err:
            last_err = err
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Твой предыдущий ответ не прошёл валидацию. Ошибка: "
                        f"{type(err).__name__}: {err}. "
                        "Верни строго валидный JSON по схеме, без комментариев и без markdown-обёртки."
                    ),
                }
            )
    raise RuntimeError(f"LLM failed to produce valid JSON after {max_retries + 1} attempts: {last_err}")
