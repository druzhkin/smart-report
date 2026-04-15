"""Backfill reports/{id}.cost.json for historical runs.

Uses overnight_summary.json for Anthropic meter data. External APIs
(Perplexity/Tavily/Firecrawl/Gamma) are estimated from scout call count.
Values are in credits (1 credit ≈ 1 ₽).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
SUMMARY = REPORTS / "overnight_summary.json"

# Heuristic: about 55% of haiku scout calls correspond to a Perplexity query
# (the rest are retries / broader rewrites that never hit the paid API).
# Official Perplexity sonar-pro: ~$0.014 per typical query → × 95 ₽/$ ≈ 1.33 ₽.
PPLX_PRO_USD = 0.014
USD_TO_RUB = 95.0
PPLX_PRO_CREDITS = PPLX_PRO_USD * USD_TO_RUB
PPLX_SHARE_OF_HAIKU = 0.55


def main() -> None:
    data = json.loads(SUMMARY.read_text(encoding="utf-8"))
    for entry in data:
        stem = entry["stem"]
        cost = entry["cost"]
        haiku_calls = cost["per_model"].get("claude-haiku-4.5", {}).get("calls", 0)
        est_pplx_calls = int(round(haiku_calls * PPLX_SHARE_OF_HAIKU))
        pplx_credits = est_pplx_calls * PPLX_PRO_CREDITS

        snap = {
            "report_id": stem,
            "goal": entry.get("query", ""),
            "currency_label": "₽",
            "per_model": cost["per_model"],
            "per_provider": {
                "anthropic": {
                    "calls": cost["total_calls"],
                    "credits": round(cost["total_usd"], 2),
                },
                "perplexity": {
                    "calls": est_pplx_calls,
                    "credits": round(pplx_credits, 2),
                    "estimated": True,
                },
            },
            "total_usd": cost["total_usd"],
            "total_credits": round(cost["total_usd"] + pplx_credits, 2),
            "total_input": cost["total_input"],
            "total_output": cost["total_output"],
            "total_calls": cost["total_calls"],
            "backfilled": True,
            "notes": (
                "Perplexity cost estimated from Haiku scout call count × 55% × 15₽ "
                "(sonar-pro per-query flat rate). Anthropic credits are authoritative."
            ),
        }
        out = REPORTS / f"{stem}.cost.json"
        out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out.name}: {snap['total_credits']:.0f} RUB "
              f"(anthropic={snap['per_provider']['anthropic']['credits']:.0f}, "
              f"pplx~{pplx_credits:.0f})")


if __name__ == "__main__":
    main()
