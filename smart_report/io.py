"""Prompts loading + per-run artefact writing. Everything artefact-related lives here."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "prompts"
RUNS_DIR = REPO_ROOT / "runs"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def extract_json(raw: str) -> Any:
    """Tolerant JSON extraction: strips ```json fences, finds first balanced {...} or [...].

    Claude on OpenRouter frequently wraps JSON in markdown fences even when asked
    for strict JSON via response_format. v2 Planner failed for this exact reason.
    """
    if raw is None:
        raise ValueError("empty LLM response")
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: pick outermost {...} or [...]
    first_obj = text.find("{")
    first_arr = text.find("[")
    candidates = [c for c in (first_obj, first_arr) if c != -1]
    if not candidates:
        raise ValueError(f"no JSON object/array found in LLM response: {text[:200]!r}")
    start = min(candidates)
    closer = "}" if start == first_obj else "]"
    end = text.rfind(closer)
    if end == -1 or end <= start:
        raise ValueError(f"unbalanced JSON in LLM response: {text[start : start + 200]!r}")
    return json.loads(text[start : end + 1])


def load_prompt(name: str) -> str:
    """Load a prompt from prompts/<name>.md. Returns '' if missing (so Track C can fill later)."""
    p = PROMPTS_DIR / f"{name}.md"
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def make_run_dir(name: str | None = None) -> Path:
    """Create runs/<name>/ (or runs/<ts>/ if name is None) and return its path."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    d = RUNS_DIR / (name or _ts())
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def write_markdown_report(path: Path, report_dict: dict) -> None:
    """Minimal markdown rendering — full formatting lives in Track D."""
    q = report_dict.get("question", {})
    blocks = report_dict.get("blocks", [])
    cross = report_dict.get("cross_links", [])
    summary = report_dict.get("summary") or {}
    lines: list[str] = []
    lines.append(f"# Report: {q.get('text', '')}\n")
    lines.append(f"_question_id: `{q.get('id', '')}`_\n")
    if summary.get("main_finding"):
        lines.append("## Executive Summary\n")
        lines.append(summary["main_finding"] + "\n")
        if summary.get("top_numbers"):
            lines.append("**Top numbers:**")
            for tn in summary["top_numbers"]:
                lines.append(
                    f"- `{tn.get('value','')}` — {tn.get('context','')} "
                    f"([src]({tn.get('source_url','')}))"
                )
            lines.append("")
        if summary.get("key_tensions"):
            lines.append("**Key tensions:**")
            for kt in summary["key_tensions"]:
                lines.append(
                    f"- {kt.get('tension','')} — A: {kt.get('pole_a','')} / "
                    f"B: {kt.get('pole_b','')}"
                )
            lines.append("")
        if summary.get("open_questions"):
            lines.append("**Open questions:**")
            for oq in summary["open_questions"]:
                lines.append(f"- {oq}")
            lines.append("")
    lines.append("## Matrix blocks\n")
    for b in blocks:
        lines.append(f"### Cell `{b['cell_id']}`")
        lines.append(f"**Conclusion:** {b['conclusion']}")
        if b.get("strongest_number"):
            lines.append(f"**Strongest number:** {b['strongest_number']}")
        if b.get("gap"):
            lines.append(f"**Gap:** {b['gap']}")
        if b.get("findings"):
            lines.append("\n**Findings:**")
            for f_ in b["findings"]:
                num = f" ({f_['number']})" if f_.get("number") else ""
                lines.append(f"- {f_['claim']}{num} — [{f_['source_type']}]({f_['source_url']})")
        lines.append("")
    if cross:
        lines.append("## Cross-domain bisociations\n")
        for cl in cross:
            lines.append(f"- **{cl['cell_a']} ↔ {cl['cell_b']}** ({cl['type']}, var=`{cl['shared_variable']}`): {cl['insight']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
