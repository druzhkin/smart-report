"""CLI wrapper for premium artifact QA.

The implementation lives in ``smart_report.exporters.premium.artifact_qa`` so
API code, tests, and the command-line checker cannot drift apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smart_report.exporters.premium.artifact_qa import main, run_qa

__all__ = ["main", "run_qa"]


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    raise SystemExit(main())
