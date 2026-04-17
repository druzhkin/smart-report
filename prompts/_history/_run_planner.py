"""One-off script: run Planner prompt through Opus, save raw output.

Usage:
    python prompts/_history/_run_planner.py v1
    python prompts/_history/_run_planner.py v2
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


QUESTION = (
    "Что определяет успех девелопера в бизнес-сегменте Москвы — "
    "бренд, скорость или продукт?"
)

QUESTION_ID = "moscow-business-success-factors"


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"v1", "v2"}:
        print("usage: _run_planner.py [v1|v2]")
        sys.exit(1)
    variant = sys.argv[1]

    env = load_env()
    api_key = env.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY missing")
        sys.exit(2)

    prompt_path = ROOT / "prompts" / "_history" / f"planner_{variant}.md"
    prompt = prompt_path.read_text(encoding="utf-8")

    user_msg = (
        "question_id: " + QUESTION_ID + "\n"
        "question: " + QUESTION + "\n"
        "\nВыдай строго JSON по output schema. Никакой прозы вокруг."
    )

    payload = {
        "model": "anthropic/claude-opus-4",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 6000,
    }

    t0 = time.time()
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://smart-report.local",
            "X-Title": "Smart Report v3 Planner bench",
        },
        json=payload,
        timeout=180,
    )
    elapsed = time.time() - t0
    print(f"status={r.status_code} elapsed={elapsed:.1f}s")
    data = r.json()
    if r.status_code != 200:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
        sys.exit(3)

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    print(
        f"tokens: prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')}"
    )

    out_md = ROOT / "prompts" / "_history" / f"planner_{variant}_output.md"
    out_md.write_text(
        f"# Planner {variant} — raw Opus output\n\n"
        f"- question: {QUESTION}\n"
        f"- elapsed: {elapsed:.1f}s\n"
        f"- tokens: prompt={usage.get('prompt_tokens')} "
        f"completion={usage.get('completion_tokens')}\n\n"
        f"---\n\n```json\n{content}\n```\n",
        encoding="utf-8",
    )
    print(f"saved -> {out_md}")


if __name__ == "__main__":
    main()
