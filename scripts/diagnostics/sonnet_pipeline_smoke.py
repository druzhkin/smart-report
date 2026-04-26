"""Pipeline-level Sonnet smoke — Block A 2.2.

Calls smart_report.llm.call_json with Sonnet on a REALISTIC-sized prompt
(~10k chars input asking for short answer). Tests whether the hang
yesterday was specific to the v4 cycle's combination of factors
(large prompt + multi-call sequence + the monkey-patch in
live_acceptance_run.py) vs the smart_report.llm wrapper itself.

Cost ~$0.005-0.01 (single Sonnet call with ~3k input tokens).
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

# Deliberately do NOT import scripts.live_acceptance_run — its module-level
# monkey-patches httpx.Response.raise_for_status globally and is a confounder
# for this diagnostic.
from smart_report.llm import call_json


SONNET = "anthropic/claude-sonnet-4.6"


# Synthetic ~3k-token prompt to exercise the actual call path with realistic
# token volume but bounded output.
LONG_PROMPT_BODY = (
    "You are a research analyst. The following text is a stub of a research "
    "report. Your job is to extract the SINGLE most important finding and "
    "respond with EXACTLY one sentence under 50 words. Do not summarise. "
    "Do not use markdown. Reply with one plain sentence.\n\n"
) + (
    "Russia's electric vehicle market in 2026 sits at a structural inflection. "
    "Three local OEMs — Moskvich (revived under Sollers), AVTOVAZ (Lada Vesta "
    "EV pilot), and Evolute (Motorinvest) — together account for under 8% of "
    "domestic EV registrations through Q1 2026, while Chinese imports led by "
    "BYD, Geely (Geely Geometry), and Chery (Chery Omoda E5) capture 78%. "
    "Localisation requirements under government decree 719 push assemblers "
    "toward higher domestic content; Moskvich's 3e model achieves 30% by 2026 "
    "via JAC partnership; AVTOVAZ targets 50% on the e-Niva by 2027. The "
    "battery supply chain remains the key constraint — domestic LFP cell "
    "production capacity is under 200 MWh/year vs 5 GWh demand projected for "
    "2027. Ministry of Industry subsidies of up to 925k RUB per locally-"
    "assembled EV (decree 1135) bridge the cost gap, but the program's 2026 "
    "fund of 7.5 bn RUB caps eligible vehicles at ~8000 units. State "
    "leasing program at GTLK adds another 2000-vehicle annual capacity. "
    "Charging infrastructure is at 5,000 public CCS stations end-2025, "
    "concentrated in Moscow / SPb / Sochi corridors; rural coverage "
    "remains negligible. Industrial buyers (city municipalities under "
    "national project 'Clean Air') represent 65% of fleet purchases; "
    "private retail is constrained by Sberbank lease pricing at 6.8% "
    "per year. The competitive frame to 2029: BYD launches local assembly "
    "in Lipetsk Q3 2026 (Atto 3 / Han); Chery reportedly negotiating "
    "Kaliningrad Avtotor partnership for E5 assembly; Geely already "
    "produces Tugella ICE locally and may pivot facility to EV. "
    "Russian OEMs face a choice: race-to-localisation with Chinese "
    "tech transfer (Moskvich/JAC playbook), full vertical integration "
    "(AVTOVAZ Vesta EV with domestic chemistry), or niche premium "
    "(Aurus Komendant). The window to consolidate position before "
    "BYD-Lipetsk volume reaches 50k units/year is approximately "
    "18 months. Successful playbooks combine: (1) cost-per-km parity "
    "with ICE under 4 RUB/km via subsidy stack; (2) battery warranty "
    "matching Chinese 8-year/160,000 km terms; (3) charging-network "
    "OEM-branded build-out (analogous to Tesla Supercharger in early "
    "USA). The risk for AVTOVAZ specifically is that decree-719 "
    "compliance may be insufficient to outcompete Lipetsk-built BYD on "
    "TCO without a 30%+ subsidy uplift over the current 925k RUB cap."
)


async def main() -> int:
    print("=== Pipeline-level Sonnet smoke (call_json path) ===")
    print(f"Prompt size: {len(LONG_PROMPT_BODY)} chars (~{len(LONG_PROMPT_BODY)//4} tokens)")
    print(f"Model: {SONNET}")
    print()

    t0 = time.time()
    try:
        result = await call_json(
            role="analyzer",
            messages=[{"role": "user", "content": LONG_PROMPT_BODY}],
            model=SONNET,
            temperature=0.2,
        )
        elapsed = time.time() - t0
        print(f"OK elapsed={elapsed:.2f}s")
        print(f"  text: {result.text[:200]}")
        print(f"  cost_rub: {result.cost_rub}")
        print(f"  tokens_in={result.tokens_in} tokens_out={result.tokens_out}")
        return 0
    except Exception as e:
        elapsed = time.time() - t0
        print(f"FAIL elapsed={elapsed:.2f}s")
        print(f"  exception: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
