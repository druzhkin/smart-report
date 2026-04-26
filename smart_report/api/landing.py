"""Static landing + /app pages router.

Landing is PUBLIC (marketing). The /app/ pages (signup/login/dashboard)
are HTML shells; their auth is enforced by the JS calling /api/auth/me
on load and bouncing to /app/login if not authenticated. The actual
data API endpoints (/api/auth/*, /api/reports/*) gate via session
cookies — see smart_report/api/auth.py and smart_report/api/reports.py.

Removed admin/admin HTTP Basic auth from the previous version — SaaS
needs the marketing page reachable to prospects without credentials.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

router = APIRouter(tags=["landing"])

_LANDING_ROOT = Path(__file__).resolve().parent.parent.parent / "landing"
_INDEX_FILENAME = "Smart Report - Landing.html"


def _safe_path(root: Path, rel_path: str) -> Path:
    """Resolve `rel_path` under `root`, refusing traversal attempts."""
    candidate = (root / rel_path).resolve()
    base = root.resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes landing root") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"not found: {rel_path}")
    return candidate


@router.get("/landing/", include_in_schema=False)
async def landing_index() -> Response:
    """Public marketing landing page."""
    index_path = _LANDING_ROOT / _INDEX_FILENAME
    if not index_path.exists():
        raise HTTPException(status_code=500, detail=f"missing landing index: {_INDEX_FILENAME}")
    return FileResponse(index_path, media_type="text/html")


@router.get("/app/{rel_path:path}", include_in_schema=False)
async def app_page(rel_path: str) -> Response:
    """Serve any file under landing/app/ (signup/login/dashboard pages + assets).

    Auth is enforced client-side: each page calls /api/auth/me and
    redirects accordingly. The data endpoints (POST /api/reports etc.)
    do server-side gating via session cookies.

    Default to dashboard.html for the /app/ root.
    """
    if not rel_path or rel_path.endswith("/"):
        rel_path = (rel_path or "") + "dashboard.html"
    app_root = _LANDING_ROOT / "app"
    target = _safe_path(app_root, rel_path)
    return FileResponse(target)


@router.get("/landing/{rel_path:path}", include_in_schema=False)
async def landing_asset(rel_path: str) -> Response:
    """Serve any file under landing/ (CSS, JSX, HTML, PNG, ...)."""
    target = _safe_path(_LANDING_ROOT, rel_path)
    return FileResponse(target)
