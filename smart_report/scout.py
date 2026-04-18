"""Scout: ScoutTask -> list[Finding] via search.search(). No LLM call in v3 skeleton —
retrieval is delegated to Perplexity, which itself is an LLM behind the curtain."""

from __future__ import annotations

from pathlib import Path

from .models import Finding, ScoutTask
from .search import search


async def scout(
    task: ScoutTask,
    *,
    mock: bool = False,
    log_dir: Path | None = None,
) -> list[Finding]:
    raw = await search(
        task.query,
        cell_id=task.cell_id,
        target_sources=task.target_sources or None,
        mock=mock,
        log_dir=log_dir,
    )
    findings: list[Finding] = []
    for r in raw:
        try:
            findings.append(Finding(**r))
        except Exception:
            # degrade gracefully — wrap as 'other' if the scout produced off-spec data
            findings.append(
                Finding(
                    claim=str(r.get("claim", ""))[:500] or "unparseable finding",
                    number=r.get("number"),
                    source_url=r.get("source_url") or "https://perplexity.ai/",
                    source_type=r.get("source_type") if r.get("source_type") in {
                        "academic", "official", "industry", "media", "other"
                    } else "other",
                    verbatim_quote=r.get("verbatim_quote"),
                )
            )
    return findings
