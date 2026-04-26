"""Week-7 v3 brief §5.1 — single $0.25 Valyu standard recon.

The brief explicitly mandates ONE standard-tier call to enumerate
Valyu's actual capability surface, with particular attention to which
domains it covers well. Day 4 (under v1 brief assumption) empirically
showed that Valyu `proprietary` returns arxiv+pubmed for an EU
regulatory query — i.e. our routing assumed coverage that doesn't
exist. The standard recon is the only authoritative way to fix that
assumption before extending the routing matrix to the v3 brief's 11
domains.

Saves the raw response + a markdown summary into docs/.
NEVER re-run — $0.25 is a one-shot per the brief's hard rule.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=REPO_ROOT / ".env")

from valyu import Valyu  # type: ignore[import-untyped]

OUT_RAW = REPO_ROOT / "runs/valyu_recon/standard_recon_response.json"
OUT_MD = REPO_ROOT / "docs/VALYU_STANDARD_RECON_FINDINGS.md"

QUERY = (
    "Provide a complete capability map of the Valyu deep research API. "
    "List: (1) all available data corpora with names, refresh frequency, "
    "licensing tier; (2) all MCP tool signatures from mcp.valyu.ai with "
    "full parameter schemas and example responses; (3) REST endpoints with "
    "request/response shapes; (4) error codes and retry semantics; "
    "(5) actual pricing per call by mode; (6) result metadata schema; "
    "(7) rate limits; (8) citation structure. Cite official Valyu docs and "
    "MCP introspection only. Special focus: enumerate datasets with "
    "regulatory primary documents (eur-lex, FDA, FCC, FTC, SEC EDGAR), "
    "name them explicitly if present, or state explicitly that they are "
    "absent from the proprietary corpus."
)


def main() -> int:
    api_key = os.environ.get("VALYU_API_KEY")
    if not api_key:
        print("ERROR: VALYU_API_KEY missing in .env")
        return 1

    print(f"=== Valyu standard recon (one-shot, $0.25) ===")
    print(f"Query length: {len(QUERY)} chars")
    print(f"Mode: search_type='all', fast_mode=False (= standard tier per Day 1 capability map)")

    OUT_RAW.parent.mkdir(parents=True, exist_ok=True)
    client = Valyu(api_key=api_key)

    print("Firing call (this can take 30-90s on standard tier)...")
    response = client.search(
        query=QUERY,
        search_type="all",
        fast_mode=False,
        max_num_results=15,
        is_tool_call=False,
    )

    print(f"  success: {getattr(response, 'success', None)}")
    print(f"  result count: {len(getattr(response, 'results', []) or [])}")

    serializable: dict = {
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "standard",
        "search_type": "all",
        "fast_mode": False,
        "query": QUERY,
        "success": getattr(response, "success", None),
        "error": getattr(response, "error", None),
        "results": [],
    }
    for r in (getattr(response, "results", None) or []):
        serializable["results"].append({
            "url": getattr(r, "url", ""),
            "title": getattr(r, "title", ""),
            "source": getattr(r, "source", ""),
            "price": float(getattr(r, "price", 0.0) or 0.0),
            "relevance_score": getattr(r, "relevance_score", None),
            "publication_date": getattr(r, "publication_date", None),
            "data_type": getattr(r, "data_type", None),
            "metadata": getattr(r, "metadata", {}) or {},
            "content": getattr(r, "content", "") if isinstance(getattr(r, "content", ""), str)
                       else json.dumps(getattr(r, "content", []), ensure_ascii=False)[:5000],
        })

    OUT_RAW.write_text(json.dumps(serializable, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    total_cost = sum(r["price"] for r in serializable["results"])
    print(f"  saved raw: {OUT_RAW}")
    print(f"  total cost (sum of per-result prices): ${total_cost:.4f}")

    # Compact markdown summary alongside the raw JSON
    lines = [
        f"# Valyu standard recon — findings ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})",
        "",
        f"Query: {QUERY[:300]}...",
        "",
        f"Mode: standard (`search_type='all', fast_mode=False`).",
        f"Per-result prices summed: **${total_cost:.4f}** (target ~$0.25).",
        f"Result count: {len(serializable['results'])}",
        "",
        "## Top results",
        "",
    ]
    for i, r in enumerate(serializable["results"][:20], 1):
        lines.append(f"### [{i}] {r['title'] or '(untitled)'}")
        lines.append(f"- url: {r['url']}")
        lines.append(f"- source: {r['source']}")
        lines.append(f"- relevance: {r['relevance_score']}")
        if r["publication_date"]:
            lines.append(f"- date: {r['publication_date']}")
        snippet = (r["content"] or "")[:600]
        lines.append("")
        lines.append(snippet)
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"  saved markdown: {OUT_MD}")
    print(f"DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
