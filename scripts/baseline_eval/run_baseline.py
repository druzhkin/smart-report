"""Run the 3 reports × 5 metrics baseline.

Writes raw responses to eval/_raw/baseline_scores.json and prints a summary.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from judge import call_judge

REPO_ROOT = Path(__file__).resolve().parents[2]
REF_DIR = REPO_ROOT / "reference"
RAW_PATH = REPO_ROOT / "eval" / "_raw" / "baseline_scores.json"

REPORTS = {
    "perplexity": REF_DIR / "perplexity_report.md",
    "openai_dr": REF_DIR / "openai_dr_report.md",
    "smart_v2": REF_DIR / "smart_report_v2_output.md",
}

METRICS = ["coverage", "groundedness", "honesty", "non_triviality", "cross_domain"]

# v2 report is ~180K chars; other reports ~30-50K. Judge context is big but
# let's cap to 140K chars (≈35K tokens) to stay safely within window & cost.
MAX_CHARS = 140_000


def load_report(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if len(text) > MAX_CHARS:
        # Take the first 70K and last 70K, mark ellipsis in the middle
        head = text[: MAX_CHARS // 2]
        tail = text[-MAX_CHARS // 2 :]
        text = head + "\n\n...[MIDDLE TRUNCATED FOR LENGTH]...\n\n" + tail
    return text


def main() -> int:
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, dict]] = {}
    total_t0 = time.time()

    for report_key, report_path in REPORTS.items():
        print(f"\n=== {report_key} ({report_path.name}) ===", flush=True)
        text = load_report(report_path)
        print(f"  loaded {len(text):,} chars", flush=True)
        results[report_key] = {}
        for metric in METRICS:
            print(f"  [{metric}] calling judge...", flush=True)
            t0 = time.time()
            resp = call_judge(metric, text)
            dt = time.time() - t0
            parsed = resp.get("parsed", {})
            score = parsed.get("score") if isinstance(parsed, dict) else None
            err = parsed.get("_parse_error") if isinstance(parsed, dict) else None
            if err:
                print(f"    ! parse error: {err}", flush=True)
            print(
                f"    score={score} ({dt:.1f}s, "
                f"in={resp.get('_prompt_tokens')} out={resp.get('_completion_tokens')})",
                flush=True,
            )
            results[report_key][metric] = resp
            # Save after each call so we don't lose progress on crash
            RAW_PATH.write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    total_dt = time.time() - total_t0
    print(f"\nDone in {total_dt:.1f}s. Raw -> {RAW_PATH}", flush=True)

    # Print compact summary table
    print("\n=== SUMMARY ===")
    print(f"{'metric':<18}" + "".join(f"{k:>15}" for k in REPORTS))
    for metric in METRICS:
        row = f"{metric:<18}"
        for report_key in REPORTS:
            parsed = results[report_key][metric].get("parsed", {})
            score = parsed.get("score") if isinstance(parsed, dict) else "?"
            row += f"{str(score):>15}"
        print(row)

    # Cost estimate (very rough)
    total_in = sum(
        r.get("_prompt_tokens") or 0
        for rep in results.values()
        for r in rep.values()
    )
    total_out = sum(
        r.get("_completion_tokens") or 0
        for rep in results.values()
        for r in rep.values()
    )
    # sonnet-4.6 via OpenRouter: ~$3/1M input, ~$15/1M output
    cost = total_in / 1_000_000 * 3 + total_out / 1_000_000 * 15
    print(f"\nTokens: in={total_in:,} out={total_out:,}  ~${cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
