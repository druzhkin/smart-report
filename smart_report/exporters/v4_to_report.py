"""Adapter: FinalReport -> uniform report dict consumed by render.py.

The dict shape is intentionally simple — one canonical layout the seven
exporter entry points share. This is the v3-native equivalent of the v2
`Report` dict, not a 1:1 port of v2 (v2 has goal/matrix.domains/block_headers
that have no meaning in v4).

Shape:

    {
      "session_id": str,
      "title": str,                     # used in file headers
      "question": str,
      "research_prompt_used": str,
      "executive_summary": {
        "main_answer": str,
        "ranking": str | None,
        "top_findings": list[str],
        "key_numbers": list[{value, metric, subject, source_url}],
        "confidence_note": str,
        "what_meta_adds": str
      },
      "sections": [                     # uniform list — renderers iterate
        {"heading": str, "body_markdown": str}
      ],
      "sources": list[{title, url, tool, reliability}],
      "metadata": dict
    }
"""

from __future__ import annotations

from typing import Any

from ..models import FinalReport


def v4_to_report_dict(final: FinalReport) -> dict[str, Any]:
    """Flatten a FinalReport into the renderer-facing dict. Side-effect-free."""
    es = final.executive_summary
    sections: list[dict[str, str]] = []

    if final.main_synthesis.strip():
        sections.append(
            {"heading": "Основной синтез", "body_markdown": final.main_synthesis.strip()}
        )
    if final.consensus_section.strip():
        sections.append(
            {"heading": "Консенсус источников", "body_markdown": final.consensus_section.strip()}
        )
    if final.conflicts_section.strip():
        sections.append(
            {"heading": "Противоречия между источниками", "body_markdown": final.conflicts_section.strip()}
        )
    if final.gaps_filled_section.strip():
        sections.append(
            {"heading": "Закрытые и оставшиеся пробелы", "body_markdown": final.gaps_filled_section.strip()}
        )

    return {
        "session_id": final.session_id,
        "title": _derive_title(final),
        "question": final.question,
        "research_prompt_used": final.research_prompt_used,
        "executive_summary": {
            "main_answer": es.main_answer,
            "ranking": es.ranking,
            "top_findings": list(es.top_findings),
            "key_numbers": [kn.model_dump() for kn in es.key_numbers],
            "confidence_note": es.confidence_note,
            "what_meta_adds": es.what_meta_adds,
        },
        "sections": sections,
        "sources": [s.model_dump() for s in final.all_sources],
        "metadata": dict(final.metadata or {}),
    }


def _derive_title(final: FinalReport) -> str:
    q = final.question.strip()
    if not q:
        return f"Smart Report v4 — {final.session_id}"
    # Cap title length for file-system friendliness on Windows.
    if len(q) > 120:
        return q[:117] + "..."
    return q
