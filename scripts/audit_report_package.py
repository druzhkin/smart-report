from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v2.audit import audit_report_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a generated report package.")
    parser.add_argument("package_dir", help="Path to reports/generated/<run_id> or reports/samples/<case_id>")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when release_status is blocked")
    args = parser.parse_args()

    summary = audit_report_package(Path(args.package_dir))
    print(json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if args.strict and summary.release_status != "released":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
