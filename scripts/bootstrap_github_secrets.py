from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from shutil import which


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env"

REQUIRED_SECRETS = [
    "OPENROUTER_API_KEY",
    "SMOKE_API_BASE",
    "SMOKE_RAGFLOW_BASE_URL",
    "SMOKE_RAGFLOW_API_KEY",
]

OPTIONAL_SECRETS = [
    "SMOKE_RAGFLOW_REPORTS_DATASET_ID",
    "SMOKE_RAGFLOW_FACTS_DATASET_ID",
    "SMOKE_RUN_REPORT",
    "SMOKE_REPORT_TIMEOUT_SEC",
]

ALIASES = {
    "SMOKE_RAGFLOW_BASE_URL": ["RAGFLOW_BASE_URL"],
    "SMOKE_RAGFLOW_API_KEY": ["RAGFLOW_API_KEY"],
    "SMOKE_RAGFLOW_REPORTS_DATASET_ID": ["RAGFLOW_REPORTS_DATASET_ID"],
    "SMOKE_RAGFLOW_FACTS_DATASET_ID": ["RAGFLOW_FACTS_DATASET_ID"],
    "SMOKE_API_BASE": ["BACKEND_PUBLIC_API_BASE", "RAILWAY_BACKEND_API_BASE"],
}


def _load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def _pick_value(key: str, file_env: dict[str, str]) -> str:
    direct = os.getenv(key, "").strip() or file_env.get(key, "").strip()
    if direct:
        return direct
    for alias in ALIASES.get(key, []):
        value = os.getenv(alias, "").strip() or file_env.get(alias, "").strip()
        if value:
            return value
    return ""


def _resolve_values(env_file: Path) -> dict[str, str]:
    file_env = _load_env_file(env_file)
    resolved: dict[str, str] = {}
    for key in REQUIRED_SECRETS + OPTIONAL_SECRETS:
        value = _pick_value(key, file_env)
        if value:
            resolved[key] = value
    return resolved


def _set_secret(name: str, value: str, repo: str | None) -> None:
    cmd = [_gh_executable(), "secret", "set", name]
    if repo:
        cmd += ["--repo", repo]
    cmd += ["--body", value]
    subprocess.run(cmd, check=True)


def _check_gh_auth() -> bool:
    try:
        proc = subprocess.run(
            [_gh_executable(), "auth", "status"], check=False, capture_output=True, text=True
        )
        return proc.returncode == 0
    except FileNotFoundError:
        return False


def _gh_executable() -> str:
    found = which("gh")
    if found:
        return found
    default_path = Path(r"C:\Program Files\GitHub CLI\gh.exe")
    if default_path.exists():
        return str(default_path)
    raise FileNotFoundError("gh executable not found")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync required GitHub Actions secrets for autonomous audit."
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--repo", default="", help="owner/repo (optional)")
    parser.add_argument("--smoke-api-base", default="", help="override SMOKE_API_BASE")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = args.repo.strip() or None
    values = _resolve_values(Path(args.env_file))
    if args.smoke_api_base.strip():
        values["SMOKE_API_BASE"] = args.smoke_api_base.strip()

    missing = [k for k in REQUIRED_SECRETS if k not in values]
    if missing:
        print("Missing required secrets:")
        for key in missing:
            print(f"- {key}")
        return 2

    targets = [k for k in REQUIRED_SECRETS + OPTIONAL_SECRETS if k in values]
    if args.dry_run:
        print("Dry run; would set secrets:")
        for key in targets:
            print(f"- {key}")
        return 0

    if not _check_gh_auth():
        print("GitHub CLI is not installed/authenticated. Install gh and run: gh auth login")
        return 3

    for key in targets:
        _set_secret(key, values[key], repo)
        print(f"Set {key}")

    print("GitHub secrets sync complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
