from __future__ import annotations

from pathlib import Path

from backend.config import settings
from backend.v2.repository import FileRunRepository


def test_cors_allowed_origins_list_parses_csv() -> None:
    original = settings.cors_allowed_origins
    settings.cors_allowed_origins = "https://smart-report.up.railway.app, https://app.example.com "
    try:
        assert settings.cors_allowed_origins_list == [
            "https://smart-report.up.railway.app",
            "https://app.example.com",
        ]
    finally:
        settings.cors_allowed_origins = original


def test_file_run_repository_defaults_to_configured_paths(tmp_path: Path) -> None:
    original_runs = settings.runs_dir
    original_reports = settings.reports_generated_dir
    settings.runs_dir = str(tmp_path / "runs")
    settings.reports_generated_dir = str(tmp_path / "reports")
    try:
        repo = FileRunRepository()
        assert repo.root == tmp_path / "runs"
        assert repo.reports_root == tmp_path / "reports"
        assert repo.root.exists()
        assert repo.reports_root.exists()
    finally:
        settings.runs_dir = original_runs
        settings.reports_generated_dir = original_reports
