"""Prompts loading + per-run artefact writing. Everything artefact-related lives here."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "prompts"
RUNS_DIR = REPO_ROOT / "runs"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
    lines: list[str] = []
    lines.append(f"# Report: {q.get('text', '')}\n")
    lines.append(f"_question_id: `{q.get('id', '')}`_\n")
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
