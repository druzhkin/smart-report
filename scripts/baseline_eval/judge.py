"""LLM-judge logic for Track C baseline eval.

Each metric gets a structured prompt that expects JSON:
  {"score": <number>, "rationale": "...", "evidence_excerpt": "..."}

Judge: anthropic/claude-sonnet-4.6 via OpenRouter.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env", override=True)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = "anthropic/claude-sonnet-4.6"

# Ten domains for Coverage
DOMAINS = [
    "product",
    "brand",
    "speed",
    "macro-finance",
    "buyer",
    "regulation",
    "competition",
    "location",
    "build-discipline",
    "service",
]

DOMAIN_DESCR_RU = {
    "product": "продукт (архитектура, планировки, инженерия, отделка)",
    "brand": "бренд и репутация девелопера",
    "speed": "скорость вывода/продаж/стройки",
    "macro-finance": "макро: ключевая ставка, проектное финансирование, ипотека",
    "buyer": "портрет покупателя (возраст, доход, семья, мотивы)",
    "regulation": "регулирование: Москомархитектура, эскроу, разрешения",
    "competition": "конкурентная среда, доли рынка, сравнение игроков",
    "location": "локация, районы, транспорт, концентрация спроса",
    "build-discipline": "дисциплина стройки: переносы сроков, ЕРЗ.РФ, ввод в эксплуатацию",
    "service": "сервис после ввода, эксплуатация, цифровые сервисы",
}


METRIC_PROMPTS: dict[str, str] = {
    "coverage": """Ты — строгий оценщик аналитических отчётов.

Вопрос отчёта: «Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?»

Оцени покрытие 10 доменов в отчёте. Домен считается ПОКРЫТЫМ, если:
- есть хотя бы одна конкретная цифра ИЛИ названный факт ИЛИ сравнение,
- НЕ просто констатация "данные отсутствуют" или "нужно исследовать",
- связан с темой отчёта.

Домены:
{domains}

Отчёт:
<<<
{report}
>>>

Верни JSON:
{{
  "score": <int 0-10, сколько доменов покрыто>,
  "rationale": "1-2 предложения: какие покрыты, какие нет",
  "evidence_excerpt": "до 250 символов из отчёта — пример покрытого домена",
  "covered_domains": ["domain1", ...],
  "missing_domains": ["domain1", ...]
}}
Только JSON, без преамбулы.""",

    "groundedness": """Ты — строгий оценщик аналитических отчётов.

Сэмплируй ДО 10 числовых утверждений из отчёта (процент, денежная сумма, число сделок/кв. м, год). Для КАЖДОГО:
1. Есть ли рядом источник (URL, имя организации)?
2. Конкретен ли он (не "данные отсутствуют")?
3. Правдоподобно ли число для данного контекста?

Верни % утверждений, которые выглядят "заземлёнными" (имеют источник + конкретны + правдоподобны).
ВАЖНО: если в отчёте мало чисел (<5), верни то, что есть, и снизь оценку.
Если большинство чисел — фразы типа "[число удалено]" или "данные отсутствуют", это 0%.

Отчёт:
<<<
{report}
>>>

Верни JSON:
{{
  "score": <int 0-100, процент заземлённых утверждений>,
  "rationale": "1-2 предложения",
  "evidence_excerpt": "одно числовое утверждение + его источник (или отсутствие источника)",
  "sampled_claims": [{{"claim": "...", "has_source": true/false, "plausible": true/false}}]
}}
Только JSON.""",

    "honesty": """Ты — строгий оценщик аналитических отчётов.

Оцени ЧЕСТНОСТЬ отчёта:
- Положительный признак: явные признания "нет данных", "данные недоступны", "ограничение", "неуточнено", "гипотеза" — когда они действительно уместны.
- Отрицательный признак: числовые утверждения БЕЗ источника, преподнесённые как факт.

Подсчитай:
- A = количество явных признаний пробелов (пусть даже "отсутствуют данные по X")
- B = количество числовых утверждений без источника

Метрика: honesty_ratio = A / max(1, A+B) × 100

Но есть нюанс: если отчёт СОСТОИТ из одних "нет данных" и не даёт содержания, это НЕ честность — это пустота. Снизь оценку, если A очень высокое, но содержательности нет.

Отчёт:
<<<
{report}
>>>

Верни JSON:
{{
  "score": <int 0-100, честность>,
  "rationale": "1-2 предложения",
  "evidence_excerpt": "цитата признания пробела ИЛИ цитата бездоказательного утверждения",
  "explicit_gaps_count": <int>,
  "unsourced_claims_count": <int>
}}
Только JSON.""",

    "non_triviality": """Ты — строгий оценщик аналитических отчётов.

Подсчитай ТРИВИАЛЬНЫЕ УТВЕРЖДЕНИЯ — это плоские банальности вида:
- "сильный бренд важен"
- "скорость без качества разрушает репутацию"
- "продукт должен удовлетворять покупателя"
- "качество имеет значение"
- "надо учитывать конкурентов"

НЕ тривиальны: конкретные цифры, названные девелоперы/проекты, механизмы (causal), нестандартные наблюдения.

ВАЖНО: чем БОЛЬШЕ тривиальности, тем ХУЖЕ. Верни score = количество тривиальных утверждений (целое число). Это обратная метрика.
Учти длину отчёта: если отчёт длинный, пропорция тривиальности важнее абсолютного числа — но всё равно считаем абсолютное число.

Отчёт:
<<<
{report}
>>>

Верни JSON:
{{
  "score": <int, количество тривиальных утверждений>,
  "rationale": "1-2 предложения",
  "evidence_excerpt": "до 250 символов — примеры тривиальностей",
  "trivial_statements": ["цитата 1", "цитата 2", ...]
}}
Только JSON.""",

    "cross_domain": """Ты — строгий оценщик аналитических отчётов.

Подсчитай КРОСС-ДОМЕННЫЕ СВЯЗИ, где явно назван общий механизм/переменная, связывающая два домена. Пример:
- "Ключевая ставка ЦБ → проектное финансирование → скорость стройки" (macro + speed, named: ключевая ставка)
- "Дефицит 2-комнатных лотов (49% vs 74% семей) → продукт проигрывает покупателю" (product + buyer, named: дефицит 2+ комнат)

НЕ засчитываются:
- "оба про рынок"
- "общее отсутствие данных"
- "бренд и продукт взаимосвязаны" без названной переменной
- связи домен-к-самому-себе

Отчёт:
<<<
{report}
>>>

Верни JSON:
{{
  "score": <int, количество named-variable кросс-связей>,
  "rationale": "1-2 предложения",
  "evidence_excerpt": "одна лучшая кросс-связь с цитатой",
  "links": [{{"domain_a": "...", "domain_b": "...", "shared_variable": "...", "quote": "..."}}]
}}
Только JSON.""",
}


def _extract_json(text: str) -> dict[str, Any]:
    """Try hard to pull a JSON object out of model output."""
    text = text.strip()
    # Strip ```json fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Find first { ... last }
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1:
        return {"_parse_error": "no braces", "_raw": text[:500]}
    blob = text[first : last + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError as e:
        return {"_parse_error": str(e), "_raw": blob[:500]}


def call_judge(
    metric: str,
    report_text: str,
    *,
    max_tokens: int = 2000,
    timeout: int = 120,
) -> dict[str, Any]:
    """Run one judge call. Returns full response dict incl. parsed JSON."""
    if not OPENROUTER_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    if metric not in METRIC_PROMPTS:
        raise ValueError(f"Unknown metric: {metric}")

    prompt_tpl = METRIC_PROMPTS[metric]
    if metric == "coverage":
        domains_desc = "\n".join(
            f"- {d}: {DOMAIN_DESCR_RU[d]}" for d in DOMAINS
        )
        prompt = prompt_tpl.format(domains=domains_desc, report=report_text)
    else:
        prompt = prompt_tpl.format(report=report_text)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/smart-report-mvp-v3",
        "X-Title": "Track C Baseline Eval",
    }
    body = {
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }
    t0 = time.time()
    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=body, timeout=timeout)
        dt = time.time() - t0
        raw = resp.json()
    except Exception as e:
        return {
            "_error": str(e),
            "_metric": metric,
            "_latency_s": round(time.time() - t0, 2),
        }

    text = ""
    try:
        text = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        pass

    parsed = _extract_json(text) if text else {"_parse_error": "empty response"}
    usage = raw.get("usage", {})

    return {
        "_metric": metric,
        "_latency_s": round(dt, 2),
        "_status": resp.status_code,
        "_prompt_tokens": usage.get("prompt_tokens"),
        "_completion_tokens": usage.get("completion_tokens"),
        "_raw_text": text,
        "parsed": parsed,
    }
