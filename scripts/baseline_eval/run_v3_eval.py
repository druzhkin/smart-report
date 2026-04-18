"""Judge one v3 run against the same 5 metrics Track C used for baselines.

Usage:
    python scripts/baseline_eval/run_v3_eval.py                  # auto-pick newest run
    python scripts/baseline_eval/run_v3_eval.py <run_dir_or_md>  # explicit
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from judge import call_judge

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "runs"
OUT_PATH = REPO_ROOT / "eval" / "_raw" / "v3_scores.json"

METRICS = ["coverage", "groundedness", "honesty", "non_triviality", "cross_domain"]


def pick_target(arg: str | None) -> Path:
    if arg:
        p = Path(arg)
        if p.is_dir():
            return p / "report.md"
        return p
    # Newest runs/<dir>/report.md by mtime
    candidates = sorted(
        RUNS_DIR.glob("*/report.md"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        raise SystemExit("no runs/<dir>/report.md found — run the pipeline first")
    return candidates[0]


def main() -> int:
    target = pick_target(sys.argv[1] if len(sys.argv) > 1 else None)
    text = target.read_text(encoding="utf-8")
    print(f"Judging {target} ({len(text):,} chars)\n", flush=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    t0 = time.time()

    for metric in METRICS:
        print(f"  [{metric}] ...", flush=True)
        tt = time.time()
        resp = call_judge(metric, text)
        dt = time.time() - tt
        parsed = resp.get("parsed", {})
        score = parsed.get("score") if isinstance(parsed, dict) else None
        err = parsed.get("_parse_error") if isinstance(parsed, dict) else None
        print(
            f"    score={score} ({dt:.1f}s, in={resp.get('_prompt_tokens')} "
            f"out={resp.get('_completion_tokens')})"
            + (f"  PARSE ERR: {err}" if err else ""),
            flush=True,
        )
        results[metric] = resp
        OUT_PATH.write_text(
            json.dumps({"_target": str(target), "scores": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    dt = time.time() - t0
    total_in = sum(r.get("_prompt_tokens") or 0 for r in results.values())
    total_out = sum(r.get("_completion_tokens") or 0 for r in results.values())
    cost = total_in / 1_000_000 * 3 + total_out / 1_000_000 * 15

    print(f"\n=== v3 SUMMARY ({dt:.1f}s, tokens in={total_in:,} out={total_out:,} ~${cost:.2f}) ===")
    for metric in METRICS:
        parsed = results[metric].get("parsed", {})
        score = parsed.get("score") if isinstance(parsed, dict) else "?"
        print(f"  {metric:<18} {score}")

    print(f"\nRaw -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
