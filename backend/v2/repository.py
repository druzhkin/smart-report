from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.v2.models import RunEvent, RunSummary, utc_now


class FileRunRepository:
    def __init__(self, *, root: str | None = None, reports_root: str | None = None) -> None:
        self.root = Path(root or settings.runs_dir)
        self.reports_root = Path(reports_root or settings.reports_generated_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.reports_root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        path = self.root / run_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "artifacts").mkdir(parents=True, exist_ok=True)
        return path

    def report_dir(self, run_id: str) -> Path:
        path = self.reports_root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _json_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def _event_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "events.jsonl"

    def _artifact_path(self, run_id: str, name: str) -> Path:
        return self.run_dir(run_id) / "artifacts" / name

    def create_run(self, summary: RunSummary) -> RunSummary:
        self.save_run(summary)
        return summary

    def save_run(self, summary: RunSummary) -> RunSummary:
        summary.updated_at = utc_now()
        self._json_path(summary.run_id).write_text(
            json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary

    def get_run(self, run_id: str) -> RunSummary | None:
        path = self._json_path(run_id)
        if not path.exists():
            return None
        return RunSummary.model_validate_json(path.read_text(encoding="utf-8"))

    def list_runs(self) -> list[RunSummary]:
        items: list[RunSummary] = []
        for path in sorted(self.root.glob("*/run.json"), reverse=True):
            try:
                items.append(RunSummary.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def append_event(self, run_id: str, event: RunEvent) -> None:
        with self._event_path(run_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def list_events(self, run_id: str) -> list[RunEvent]:
        path = self._event_path(run_id)
        if not path.exists():
            return []
        events: list[RunEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(RunEvent.model_validate_json(line))
            except Exception:
                continue
        return events

    def save_artifact(self, run_id: str, name: str, payload: Any) -> Path:
        path = self._artifact_path(run_id, name)
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        elif isinstance(payload, bytes):
            path.write_bytes(payload)
        else:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_artifact(self, run_id: str, name: str) -> Any:
        path = self._artifact_path(run_id, name)
        if not path.exists():
            return None
        if path.suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        return path.read_text(encoding="utf-8")

    def write_report_file(self, run_id: str, filename: str, content: str | bytes) -> Path:
        path = self.report_dir(run_id) / filename
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def list_report_files(self, run_id: str) -> list[Path]:
        path = self.report_dir(run_id)
        if not path.exists():
            return []
        return [item for item in path.iterdir() if item.is_file()]
