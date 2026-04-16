"""Single nopplx run to measure improvement."""
from __future__ import annotations

import asyncio
import sys
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from bench_ab import run_once


async def main() -> None:
    r = await run_once(False, "nopplx_v3")
    print("\n--- RESULT ---\n" + json.dumps(r, ensure_ascii=False, indent=2))
    Path("reports/ab_nopplx_v3_result.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
