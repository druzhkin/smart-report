"""Local smoke for the streaming-DR pipeline using cheap perplexity/sonar-pro.

Verifies end-to-end:
  1. submit_*_deep_research kicks off background task
  2. Streaming runner accumulates chars
  3. PG-equivalent (in-memory store) gets partial flushes
  4. On completion, source_reports has the full markdown

Cost: ~$0.005 per run (sonar-pro short answer). Doesn't use the
deep-research model — same streaming code path, just much cheaper
and faster (returns in ~10s vs 5-15min for sonar-deep-research).
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
from smart_report.sources import llm_deepresearch as dr  # noqa: E402
from smart_report.v4_orchestrator import V4SessionStore  # noqa: E402


async def main() -> int:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("FATAL: OPENROUTER_API_KEY not set"); return 2

    store = V4SessionStore()
    sid = "smoke-stream-1"
    session = V4Session(
        session_id=sid,
        raw_question="What is 2+2? Answer briefly.",
        status="created",
        created_at=datetime.now(timezone.utc),
    )
    store._sessions[sid] = session  # type: ignore[attr-defined]

    # SMOKE_MODEL: cheap | deep | openai
    smoke = os.environ.get("SMOKE_MODEL", "cheap")
    if smoke == "deep":
        dr.PERPLEXITY_DR_MODELS = {"smoke": ("perplexity/sonar-deep-research", 0.10, 5, 15)}
        info = dr.submit_perplexity_deep_research(
            session.raw_question, mode="smoke",
            session_id=sid, store=store,
        )
    elif smoke == "openai":
        dr.OPENAI_DR_MODELS = {"smoke": ("openai/o4-mini-deep-research", 0.50, 5, 10)}
        info = dr.submit_openai_deep_research(
            session.raw_question, mode="smoke",
            session_id=sid, store=store,
        )
    else:
        dr.PERPLEXITY_DR_MODELS = {"smoke": ("perplexity/sonar-pro", 0.01, 0, 1)}
        info = dr.submit_perplexity_deep_research(
            session.raw_question, mode="smoke",
            session_id=sid, store=store,
        )
    print(f"submitted: task_id={info.task_id}")

    # Poll partial_content from store every 2s until task is done or timeout.
    smoke_mode = os.environ.get("SMOKE_MODEL", "cheap")
    timeout_s = 90 if smoke_mode == "cheap" else 1500  # deep & openai both reasoning models, can take 10-25 min
    deadline = time.time() + timeout_s
    last_chars = -1
    while time.time() < deadline:
        await asyncio.sleep(2)
        s = store.get(sid)
        # Job entry while running, source_reports entry when completed.
        running_job = next(
            (j for j in (s.pending_dr_jobs or []) if j.get("task_id") == info.task_id),
            None,
        )
        if running_job:
            chars = running_job.get("partial_chars", 0)
            if chars != last_chars:
                print(f"  partial: {chars} chars, state={running_job.get('state')}")
                last_chars = chars
        else:
            # Removed from pending = completed (or failed)
            for u in (s.source_reports or []):
                if info.task_id[:8] in u.filename:
                    print(f"\n✓ COMPLETED")
                    print(f"  filename: {u.filename}")
                    print(f"  word_count: {u.word_count}")
                    print(f"  first 300 chars of content:")
                    print(f"  {u.content[:300]!r}")
                    return 0
            print("\n✗ task removed from pending but no matching source_report found")
            return 1

    print("\n✗ TIMEOUT after 90s")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
