"""Block A 2.2 — Sonnet hang root cause: response_format=json_object?

The v4 synthesizer call uses response_format={"type": "json_object"}.
Smoke tests without that parameter pass cleanly even at 100k chars.
This probes whether json_object response_format is what hangs Sonnet
4.6 via OpenRouter today.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=REPO_ROOT / ".env")

from smart_report.llm import call_json

SONNET = "anthropic/claude-sonnet-4.6"


async def probe(use_json_format: bool, ask_long: bool) -> dict:
    if ask_long:
        prompt = (
            "Generate a JSON object with two fields: 'summary' (a 200-word "
            "analysis paragraph) and 'findings' (an array of 5 objects, each "
            "with 'title' (10 words) and 'detail' (40 words)). Output JSON only."
        )
    else:
        prompt = "Reply with JSON exactly: {\"status\": \"OK\"}"

    label = (
        f"json_format={use_json_format} ask_long={ask_long}"
    )
    print(f"\n[probe] {label}")
    t0 = time.time()
    try:
        kwargs = {}
        if use_json_format:
            kwargs["response_format"] = {"type": "json_object"}
        r = await asyncio.wait_for(
            call_json(
                role="synthesizer",
                messages=[
                    {"role": "system", "content": "You are an analyst. Reply only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=SONNET,
                temperature=0.2,
                **kwargs,
            ),
            timeout=180.0,
        )
        elapsed = time.time() - t0
        # Try to validate it's actually JSON
        try:
            parsed = json.loads(r.text)
            keys = list(parsed.keys()) if isinstance(parsed, dict) else "(non-dict)"
            json_ok = True
        except Exception:
            keys = "(JSON_DECODE_ERR)"
            json_ok = False
        print(f"  OK elapsed={elapsed:.1f}s tokens_in={r.tokens_in} tokens_out={r.tokens_out} cost_rub={r.cost_rub}")
        print(f"  json_parse_ok={json_ok} top_keys={keys}")
        return {"label": label, "ok": True, "elapsed": elapsed, "json_ok": json_ok}
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        print(f"  HANG TIMEOUT elapsed={elapsed:.1f}s — confirms response_format issue")
        return {"label": label, "ok": False, "elapsed": elapsed, "reason": "timeout"}


async def main() -> int:
    print("=== Sonnet 4.6 response_format=json_object probe ===")
    # Cheapest first; escalate only if cheaper variant works
    cases = [
        (False, False),  # baseline: no json_format, short ask
        (True, False),   # json_format on, short ask (key isolation)
        (True, True),    # json_format on, long structured output (close to synth shape)
    ]
    results = []
    for use_json, ask_long in cases:
        r = await probe(use_json, ask_long)
        results.append(r)
        if not r["ok"]:
            print(f"\n[stop] hang detected at: {r['label']}")
            break
    print("\n=== Summary ===")
    for r in results:
        verdict = "OK" if r["ok"] else "HANG"
        print(f"  {r['label']}: {verdict} ({r['elapsed']:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
