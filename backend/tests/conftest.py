"""Shared test configuration and fixtures."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

# Ensure project root is in sys.path so `from backend.xxx import ...` works
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Disable external service tracing/connections before any imports
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("PERPLEXITY_API_KEY", "test-key")
os.environ.setdefault("RAGFLOW_API_KEY", "")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("POSTGRES_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("OUTPUTS_DIR", "/tmp/smart-report-test-outputs")

_LOCAL_TMP = ROOT / "backend" / ".pytest-temp"
_LOCAL_TMP.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TMP", str(_LOCAL_TMP))
os.environ.setdefault("TEMP", str(_LOCAL_TMP))
os.environ.setdefault("TMPDIR", str(_LOCAL_TMP))
tempfile.tempdir = str(_LOCAL_TMP)


@pytest.fixture(autouse=True)
def use_cheap_models(monkeypatch):
    """Override all MODEL_MAP entries to openai/gpt-4o-mini for cost efficiency."""
    import backend.pipeline.model_router as mr

    cheap = "openai/gpt-4o-mini"
    monkeypatch.setattr(mr, "MODEL_MAP", {task: cheap for task in mr.AgentTask})


@pytest.fixture
def tmp_path() -> Path:
    path = ROOT / "backend" / ".test-artifacts" / str(uuid.uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_INTEGRATION_TESTS") == "1":
        return

    skip_integration = pytest.mark.skip(reason="integration tests are opt-in; set RUN_INTEGRATION_TESTS=1")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
