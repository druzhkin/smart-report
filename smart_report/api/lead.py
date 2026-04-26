"""Lead-capture endpoint for the landing page form (admin/admin gated UI).

POST /api/lead — accepts {package, name, email, message?, source?, ts_iso?}
and appends one JSON line per submission to runs/leads/leads.jsonl.
Also writes a per-lead JSON file for ad-hoc inspection.

No auth on this endpoint itself — the landing page sits behind admin/admin
HTTP Basic auth, so anyone reaching the form is already authed. Adding
double-auth would just break fetch() from the page.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger("smart_report.api.lead")

router = APIRouter(prefix="/api", tags=["lead"])

_LEADS_DIR = Path(__file__).resolve().parent.parent.parent / "runs" / "leads"
_LEADS_JSONL = _LEADS_DIR / "leads.jsonl"

# Conservative caps so a malicious payload can't pollute the disk.
_MAX_NAME_LEN = 200
_MAX_MESSAGE_LEN = 4000
_MAX_PACKAGE_LEN = 80
_MAX_EMAIL_LEN = 200

# Pragmatic email pattern — pydantic's EmailStr would require the
# `email-validator` package; a regex avoids the dep for this demo-grade
# capture. Anything that LOOKS like an email passes; we don't verify
# deliverability.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class LeadIn(BaseModel):
    package: str = Field(default="generic", max_length=_MAX_PACKAGE_LEN)
    package_title: Optional[str] = Field(default=None, max_length=200)
    name: str = Field(default="", max_length=_MAX_NAME_LEN)
    email: str = Field(..., max_length=_MAX_EMAIL_LEN)
    message: str = Field(default="", max_length=_MAX_MESSAGE_LEN)
    source: str = Field(default="landing", max_length=80)
    ts_iso: Optional[str] = None  # browser-side timestamp (informational)

    @field_validator("name", "message", "package", "package_title", "source", mode="before")
    @classmethod
    def _strip(cls, v):
        if v is None:
            return v
        return str(v).strip()

    @field_validator("email", mode="before")
    @classmethod
    def _email_shape(cls, v):
        if v is None:
            raise ValueError("email is required")
        s = str(v).strip()
        if not _EMAIL_RE.match(s):
            raise ValueError("invalid email format")
        return s


class LeadOut(BaseModel):
    ok: bool
    id: str


def _safe_email_slug(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", email)[:60]


@router.post("/lead", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def submit_lead(payload: LeadIn, request: Request) -> LeadOut:
    """Append a lead to runs/leads/. Returns {ok, id}."""
    _LEADS_DIR.mkdir(parents=True, exist_ok=True)
    server_ts = datetime.now(timezone.utc).isoformat()
    lead_id = uuid.uuid4().hex[:12]
    record = {
        "id": lead_id,
        "received_at": server_ts,
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:300],
        **payload.model_dump(),
    }
    try:
        with _LEADS_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        per_lead = _LEADS_DIR / f"{server_ts.replace(':', '-')}_{_safe_email_slug(str(payload.email))}_{lead_id}.json"
        per_lead.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover — fs error on Railway
        log.exception("lead persist failed: %s", exc)
        raise HTTPException(status_code=500, detail="lead store unavailable") from exc

    log.info("lead captured: id=%s package=%s email=%s", lead_id, payload.package, payload.email)
    return LeadOut(ok=True, id=lead_id)
