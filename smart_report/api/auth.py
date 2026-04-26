"""Email + password auth for the SaaS UI.

User model lives in `data/users.json` — a single JSON file mapping
email → {password_hash, created_at}. bcrypt for passwords. Sessions
ride on Starlette's SessionMiddleware (signed cookie via itsdangerous,
SECRET_KEY from env or a per-process default for local dev).

This is demo-grade SaaS auth — single JSON file, no DB, no email
verification, no password reset. Good enough for self-serve report
creation; not for production with real customers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger("smart_report.api.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_USERS_PATH = _DATA_DIR / "users.json"
_USERS_LOCK = threading.Lock()

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MIN_PW_LEN = 6
_MAX_PW_LEN = 200
_MAX_EMAIL_LEN = 200


def _load_users() -> dict:
    if not _USERS_PATH.exists():
        return {}
    try:
        return json.loads(_USERS_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.exception("users.json corrupt, starting empty")
        return {}


def _save_users(users: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _USERS_PATH.write_text(
        json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("ascii")


def _verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("ascii"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class _Credentials(BaseModel):
    email: str = Field(..., max_length=_MAX_EMAIL_LEN)
    password: str = Field(..., min_length=_MIN_PW_LEN, max_length=_MAX_PW_LEN)

    @field_validator("email", mode="before")
    @classmethod
    def _check_email(cls, v):
        if v is None:
            raise ValueError("email is required")
        s = str(v).strip().lower()
        if not _EMAIL_RE.match(s):
            raise ValueError("invalid email format")
        return s


class AuthOut(BaseModel):
    ok: bool
    email: str


class MeOut(BaseModel):
    authenticated: bool
    email: Optional[str] = None


# ---------------------------------------------------------------------------
# Session helpers (use Starlette SessionMiddleware via request.session)
# ---------------------------------------------------------------------------


def current_user(request: Request) -> Optional[dict]:
    """Return {email, ...user record} or None. Used as FastAPI dependency."""
    sess = getattr(request, "session", {}) or {}
    email = sess.get("user_email")
    if not email:
        return None
    users = _load_users()
    rec = users.get(email)
    if rec is None:
        # Stale cookie pointing to a deleted user — clear session
        sess.pop("user_email", None)
        return None
    return {"email": email, **rec}


def require_user(request: Request) -> dict:
    user = current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/signup", response_model=AuthOut, status_code=201)
async def signup(creds: _Credentials, request: Request) -> AuthOut:
    email = _normalize_email(creds.email)
    with _USERS_LOCK:
        users = _load_users()
        if email in users:
            raise HTTPException(status_code=409, detail="email already registered")
        users[email] = {
            "password_hash": _hash_password(creds.password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_users(users)
    request.session["user_email"] = email
    log.info("signup ok: email=%s", email)
    return AuthOut(ok=True, email=email)


@router.post("/login", response_model=AuthOut)
async def login(creds: _Credentials, request: Request) -> AuthOut:
    email = _normalize_email(creds.email)
    users = _load_users()
    rec = users.get(email)
    if rec is None or not _verify_password(creds.password, rec["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid email or password")
    request.session["user_email"] = email
    log.info("login ok: email=%s", email)
    return AuthOut(ok=True, email=email)


@router.post("/logout")
async def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=MeOut)
async def me(request: Request) -> MeOut:
    user = current_user(request)
    if user is None:
        return MeOut(authenticated=False)
    return MeOut(authenticated=True, email=user["email"])
