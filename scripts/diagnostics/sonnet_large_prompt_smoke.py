"""Block A 2.2 — Sonnet hang diagnosis: prompt-size threshold test.

Pipeline-level call_json with progressively larger prompts to find the
threshold where Sonnet via OpenRouter starts hanging. Q1/Q3 hangs in
the v4 cycle were ALL at the synthesizer first call (which sends
~30-150k tokens of context). The smaller call_json smoke (3k tokens)
returned cleanly in 4.7s.
"""

from __future__ import annotations

import asyncio
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

# Synthetic filler — repeat to scale prompt size predictably
_FILLER_PARA = (
    "Russia's electric vehicle market in 2026 sits at a structural "
    "inflection. Three local OEMs — Moskvich, AVTOVAZ, Evolute — together "
    "account for under 8% of EV registrations through Q1 2026, while "
    "Chinese imports led by BYD, Geely, and Chery capture 78%. Localisation "
    "requirements push assemblers toward higher domestic content; Moskvich "
    "achieves 30% by 2026 via JAC partnership; AVTOVAZ targets 50% on the "
    "e-Niva by 2027. The battery supply chain remains the key constraint. "
)


async def probe(target_chars: int) -> dict:
    body = (
        "You are a research analyst. Extract THE single most important "
        "finding from the following report stub. Reply with ONE plain "
        "sentence under 50 words.\n\n"
    )
    while len(body) < target_chars:
        body += _FILLER_PARA
    body = body[:target_chars]

    print(f"\n[probe] target={target_chars} actual={len(body)} (~{len(body)//4} tokens)")
    t0 = time.time()
    try:
        r = await asyncio.wait_for(
            call_json(
                role="analyzer",
                messages=[{"role": "user", "content": body}],
                model=SONNET,
                temperature=0.2,
            ),
            timeout=180.0,  # 3 min per probe
        )
        elapsed = time.time() - t0
        print(f"  OK elapsed={elapsed:.1f}s tokens_in={r.tokens_in} cost_rub={r.cost_rub}")
        print(f"  text: {r.text[:140]}")
        return {"chars": target_chars, "ok": True, "elapsed": elapsed}
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        print(f"  HANG TIMEOUT elapsed={elapsed:.1f}s — confirms prompt-size threshold")
        return {"chars": target_chars, "ok": False, "elapsed": elapsed, "reason": "timeout_180s"}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  FAIL elapsed={elapsed:.1f}s exc={type(e).__name__}: {e}")
        return {"chars": target_chars, "ok": False, "elapsed": elapsed, "reason": str(e)[:200]}


async def main() -> int:
    print("=== Sonnet 4.6 prompt-size threshold probe ===")
    # Step up: 3k (known good), 30k, 100k. Stop when first hang.
    sizes = [3000, 30000, 100000]
    results = []
    for s in sizes:
        r = await probe(s)
        results.append(r)
        if not r["ok"]:
            print(f"\n[stop] hang detected at {s} chars → not escalating further")
            break
    print("\n=== Summary ===")
    for r in results:
        verdict = "OK" if r["ok"] else "HANG"
        print(f"  {r['chars']:>6} chars: {verdict} ({r['elapsed']:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
