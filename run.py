"""CLI entrypoint. Usage:

    python run.py --dry-run "Your question here"
    python run.py "Your question here"
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure UTF-8 stdio on Windows consoles (cp866/cp1251 mangles cyrillic otherwise)
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

import click  # noqa: E402

from smart_report.orchestrator import run as run_orchestrator


@click.command()
@click.argument("question", type=str)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Use mocked LLM + search responses. No API calls, $0.",
)
def cli(question: str, dry_run: bool) -> None:
    """Run the Smart Report pipeline on a question."""
    if not question.strip():
        click.echo("error: empty question", err=True)
        sys.exit(2)

    report = asyncio.run(run_orchestrator(question, dry_run=dry_run))
    run_dir = report.metadata.get("run_dir", "?")
    click.echo(f"ok — {len(report.blocks)} blocks, {len(report.cross_links)} cross-links")
    click.echo(f"artefacts: {run_dir}")


if __name__ == "__main__":
    cli()
