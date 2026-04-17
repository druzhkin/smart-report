"""End-to-end dry-run — no real API calls, verifies the Report shape is valid."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from smart_report.models import Report
from smart_report.orchestrator import run as run_orchestrator


@pytest.mark.asyncio
async def test_dry_run_end_to_end() -> None:
    question = "Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?"
    report = await run_orchestrator(question, dry_run=True)

    assert isinstance(report, Report)
    assert report.question.text == question
    assert report.question.id.endswith(report.question.id.split("-", 2)[-1])

    # Matrix non-empty
    assert len(report.matrix.cells) >= 1
    assert len(report.matrix.domains) >= 1

    # One block per cell
    assert len(report.blocks) == len(report.matrix.cells)
    for b in report.blocks:
        assert b.conclusion, "conclusion must be non-empty"
        assert isinstance(b.findings, list)

    # Cross-links optional but must be list
    assert isinstance(report.cross_links, list)

    # Artefacts exist on disk
    run_dir = Path(report.metadata["run_dir"])
    assert (run_dir / "raw.json").exists()
    assert (run_dir / "report.md").exists()
    assert (run_dir / "llm_log.jsonl").exists()

    # raw.json round-trips as a Report
    raw = json.loads((run_dir / "raw.json").read_text(encoding="utf-8"))
    reloaded = Report(**raw)
    assert reloaded.question.id == report.question.id


@pytest.mark.asyncio
async def test_dry_run_never_hits_network(monkeypatch) -> None:
    """If a dev accidentally removes mock=True plumbing, this test will catch it."""
    import httpx

    class _Fail(httpx.AsyncClient):
        async def post(self, *a, **kw):  # type: ignore[override]
            raise AssertionError("network call attempted in dry-run mode")

    monkeypatch.setattr(httpx, "AsyncClient", _Fail)
    report = await run_orchestrator("Quick test question", dry_run=True)
    assert report.blocks, "expected blocks even in dry-run"
