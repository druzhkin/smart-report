from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def artifact_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / ".test-artifacts" / f"optimizer-{uuid.uuid4()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.asyncio
async def test_optimizer_selects_best_variant(monkeypatch, artifact_dir: Path):
    from backend.prompt_library import optimizer

    prompts_dir = artifact_dir / "prompts"
    few_shot_dir = artifact_dir / "prompt_library" / "knowledge_base" / "few_shot_examples"
    performance_log = artifact_dir / "prompt_library" / "knowledge_base" / "performance_log.jsonl"

    prompts_dir.mkdir(parents=True, exist_ok=True)
    few_shot_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = prompts_dir / "supervisor_system.txt"
    prompt_path.write_text("original prompt", encoding="utf-8")

    performance_entries = [
        {
            "task_id": "run-1",
            "critic_score": 6.2,
            "metadata": {"prompt_file": "supervisor_system"},
        },
        {
            "task_id": "run-2",
            "critic_score": 6.8,
            "metadata": {"prompt_file": "supervisor_system"},
        },
    ]
    performance_log.parent.mkdir(parents=True, exist_ok=True)
    performance_log.write_text(
        "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in performance_entries),
        encoding="utf-8",
    )

    examples = {
        "type": "market_analysis",
        "examples": [
            {"input": f"example {idx}", "output": {"title": f"Title {idx}", "sections": ["A", "B"]}}
            for idx in range(5)
        ],
    }
    (few_shot_dir / "market_analysis.json").write_text(
        json.dumps(examples, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(optimizer, "PROMPTS_DIR", prompts_dir)
    monkeypatch.setattr(optimizer, "FEW_SHOT_DIR", few_shot_dir)
    monkeypatch.setattr(optimizer, "PERFORMANCE_LOG", performance_log)

    generate_mock = AsyncMock(return_value=["variant one", "variant two", "variant three"])
    score_mock = AsyncMock(side_effect=[6.5, 8.4, 7.1])

    monkeypatch.setattr(optimizer, "_generate_variants", generate_mock)
    monkeypatch.setattr(optimizer, "_score_variant", score_mock)

    await optimizer.run_apo_optimization()

    assert prompt_path.read_text(encoding="utf-8") == "variant two"
    assert generate_mock.await_count == 1
    assert score_mock.await_count == 3

    first_scored_examples = score_mock.await_args_list[0].args[1]
    assert len(first_scored_examples) == 5

    log_lines = performance_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 3
    optimizer_entry = json.loads(log_lines[-1])
    assert optimizer_entry["metadata"]["optimizer_run"] is True
    assert optimizer_entry["metadata"]["applied"] is True
    assert optimizer_entry["metadata"]["improvement_delta"] == pytest.approx(1.9)
    assert optimizer_entry["metadata"]["previous_avg_critic_score"] == pytest.approx(6.5)
    assert optimizer_entry["metadata"]["new_avg_critic_score"] == pytest.approx(8.4)
