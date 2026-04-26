"""Sonnet 4.6 smoke test — Block A 2.1 of session unblock task.

Minimal direct-HTTP call (NOT through pipeline). Tests whether the hang
yesterday was OpenRouter-side or our async/pipeline-side.

Usage: python -u -m scripts.diagnostics.sonnet_smoke

Cost ~$0.001 per call. If smoke passes <5s -> bug in pipeline (2.2).
If smoke hangs 30s+ -> OpenRouter side (2.3).
"""

from __future__ import annotations

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

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=REPO_ROOT / ".env")

MODELS_TO_PROBE = [
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-haiku-4.5",
]


def smoke(model: str, key: str, timeout: float = 30.0) -> dict:
    t0 = time.time()
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "max_tokens": 10,
            },
            timeout=timeout,
        )
        elapsed = time.time() - t0
        return {
            "model": model,
            "status": r.status_code,
            "elapsed_s": round(elapsed, 2),
            "ok": r.status_code == 200,
            "body_preview": r.text[:200],
        }
    except httpx.TimeoutException as e:
        elapsed = time.time() - t0
        return {
            "model": model,
            "status": "TIMEOUT",
            "elapsed_s": round(elapsed, 2),
            "ok": False,
            "body_preview": f"timed out after {timeout}s: {type(e).__name__}",
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "model": model,
            "status": f"ERROR ({type(e).__name__})",
            "elapsed_s": round(elapsed, 2),
            "ok": False,
            "body_preview": str(e)[:200],
        }


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("ERROR: OPENROUTER_API_KEY missing in .env")
        return 1

    print("=== Sonnet smoke probe ===")
    print(f"OPENROUTER_API_KEY present: {key[:10]}...")
    print()

    for model in MODELS_TO_PROBE:
        print(f"[smoke] probing {model} ...")
        r = smoke(model, key, timeout=30.0)
        verdict = "OK" if r["ok"] else "FAIL"
        print(f"  {verdict} status={r['status']} elapsed={r['elapsed_s']}s")
        print(f"  body: {r['body_preview']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
