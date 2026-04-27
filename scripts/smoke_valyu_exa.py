"""Local smoke for Valyu Research.

Verifies submit + poll loop + result extraction. Doesn't go through
the FastAPI endpoint — calls submit_async_research / try_collect_*
directly. Uses Valyu Fast ($0.10) for minimum cost.

Requires VALYU_API_KEY in env.

Note: Exa requires EXA_API_KEY which we don't have locally — Exa
verification will need to happen in prod.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

from smart_report.models import V4Session  # noqa: E402
from smart_report.sources.auto_dr import (  # noqa: E402
    submit_async_research,
    try_collect_async_research,
)
from smart_report.v4_orchestrator import V4SessionStore  # noqa: E402


async def main() -> int:
    if not os.environ.get("VALYU_API_KEY"):
        print("FATAL: VALYU_API_KEY not set"); return 2

    store = V4SessionStore()
    sid = "smoke-valyu-1"
    session = V4Session(
        session_id=sid,
        raw_question="What is the capital of France?",
        status="created",
        created_at=datetime.now(timezone.utc),
    )
    store._sessions[sid] = session  # type: ignore[attr-defined]

    print("submitting Valyu fast (cheap)...")
    sub = await submit_async_research(
        "valyu", session.raw_question, mode="fast",
        session_id=sid, store=store,
    )
    print(f"submitted: task_id={sub.task_id}")

    deadline = time.time() + 600  # 10 min cap
    last_state = None
    while time.time() < deadline:
        await asyncio.sleep(15)
        poll = await try_collect_async_research(
            sub.task_id, service="valyu", mode="fast",
        )
        if poll.state != last_state:
            print(f"  state={poll.state}  msg={poll.message}")
            last_state = poll.state
        if poll.state == "completed":
            res = poll.result
            print(f"\n✓ COMPLETED")
            print(f"  filename: {res.upload.filename}")
            print(f"  word_count: {res.upload.word_count}")
            print(f"  source_count: {res.source_count}")
            print(f"  cost_usd: ${res.cost_usd}")
            print(f"  first 300 chars:")
            print(f"  {res.upload.content[:300]!r}")
            return 0
        if poll.state == "failed":
            print(f"\n✗ FAILED: {poll.error}")
            return 1

    print("\n✗ TIMEOUT")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
