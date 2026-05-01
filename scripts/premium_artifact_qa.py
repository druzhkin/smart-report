"""CLI wrapper for premium artifact QA.

The implementation lives in ``smart_report.exporters.premium.artifact_qa`` so
API code, tests, and the command-line checker cannot drift apart.
"""

from __future__ import annotations

from smart_report.exporters.premium.artifact_qa import main, run_qa

__all__ = ["main", "run_qa"]


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    raise SystemExit(main())
