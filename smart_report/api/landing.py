"""Static landing page router with HTTP Basic auth (admin/admin).

Serves the React+Babel UMD landing site checked in under `landing/` at
the project root. Auth is HTTP Basic with hard-coded admin/admin
credentials per user request — INTENTIONALLY trivial; this is a
demo-grade gate, not production access control.

Routes:
  GET /landing/          → index.html (Smart Report - Landing.html)
  GET /landing/{path}    → serve any file under landing/ directory

The hard-coded credentials live in this file rather than env vars so
the deployment story is "git pull, run, browse" without secrets
plumbing.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

router = APIRouter(prefix="/landing", tags=["landing"])

_security = HTTPBasic()

# Demo credentials per user request. Comparing with secrets.compare_digest
# avoids timing-attack leakage; not that it matters at this stage but it's
# the right tool.
_ADMIN_USER = "admin"
_ADMIN_PASS = "admin"


# Project-root / landing/ directory (where the ZIP was extracted).
_LANDING_ROOT = Path(__file__).resolve().parent.parent.parent / "landing"

# Default landing entry point — the HTML file from the ZIP.
_INDEX_FILENAME = "Smart Report - Landing.html"


def _verify_admin(creds: HTTPBasicCredentials = Depends(_security)) -> str:
    user_ok = secrets.compare_digest(creds.username, _ADMIN_USER)
    pass_ok = secrets.compare_digest(creds.password, _ADMIN_PASS)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


def _safe_path(rel_path: str) -> Path:
    """Resolve `rel_path` under the landing root, refusing escape attempts."""
    candidate = (_LANDING_ROOT / rel_path).resolve()
    root = _LANDING_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes landing root") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"not found: {rel_path}")
    return candidate


@router.get("/", include_in_schema=False)
async def landing_index(_user: str = Depends(_verify_admin)) -> Response:
    """Serve the default landing index HTML."""
    index_path = _LANDING_ROOT / _INDEX_FILENAME
    if not index_path.exists():
        raise HTTPException(status_code=500, detail=f"missing landing index: {_INDEX_FILENAME}")
    return FileResponse(index_path, media_type="text/html")


@router.get("/{rel_path:path}", include_in_schema=False)
async def landing_asset(rel_path: str, _user: str = Depends(_verify_admin)) -> Response:
    """Serve any file under landing/ (CSS, JSX, HTML, PNG, ...).

    Path traversal attempts (e.g. `..//etc/passwd`) get a 400 via the
    relative_to check in `_safe_path`.
    """
    target = _safe_path(rel_path)
    return FileResponse(target)
