"""Smoke-test that core pipeline modules import on a clean checkout.

Guards against the 2026-04-17 near-miss where 7 .py files were imported from
tracked code but never `git add`-ed. Any ImportError → non-zero exit.

Usage:
    python scripts/check_imports.py

Run before `git push` or in CI on a clean container.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODULES = [
    "models",
    "config",
    "llm",
    "search",
    "corpus_fetch",
    "corpus_mapper",
    "orchestrator",
    "export",
    "export_docx",
    "validators",
    "api.main",
    "agents.planner",
    "agents.scout",
    "agents.analyst",
    "agents.bisociator",
    "agents.summarizer",
    "agents.intake",
    "agents.contrarian",
    "agents.consensus",
    "agents.quant_extractor",
]


def main() -> int:
    failed: list[tuple[str, str]] = []
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 — any import failure is fatal
            failed.append((name, f"{type(exc).__name__}: {exc}"))

    if failed:
        print(f"FAIL: {len(failed)}/{len(MODULES)} modules failed to import", file=sys.stderr)
        for name, err in failed:
            print(f"  {name}: {err}", file=sys.stderr)
        return 1

    print(f"OK: {len(MODULES)} modules imported cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
