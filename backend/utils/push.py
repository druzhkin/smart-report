from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config import normalize_database_url, settings

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - fallback for constrained test envs
    class WebPushException(Exception):
        pass

    def webpush(*args, **kwargs) -> None:
        raise RuntimeError("pywebpush is not installed")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS push_subscriptions (
    session_id TEXT PRIMARY KEY,
    subscription_json TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def _get_db_url() -> str:
    return normalize_database_url(settings.postgres_url, async_driver=True)


async def _ensure_table(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_TABLE_SQL))


async def save_push_subscription(session_id: str, subscription: dict[str, Any]) -> None:
    engine = create_async_engine(_get_db_url(), future=True)
    try:
        await _ensure_table(engine)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO push_subscriptions (session_id, subscription_json, created_at)
                    VALUES (:session_id, :subscription_json, :created_at)
                    ON CONFLICT(session_id) DO UPDATE SET
                        subscription_json = excluded.subscription_json,
                        created_at = excluded.created_at
                    """
                ),
                {
                    "session_id": session_id,
                    "subscription_json": json.dumps(subscription, ensure_ascii=False),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
    finally:
        await engine.dispose()


async def get_push_subscription(session_id: str) -> dict[str, Any] | None:
    engine = create_async_engine(_get_db_url(), future=True)
    try:
        await _ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT subscription_json FROM push_subscriptions WHERE session_id = :session_id"
                ),
                {"session_id": session_id},
            )
            row = result.first()
            if not row:
                return None
            return json.loads(row[0])
    finally:
        await engine.dispose()


async def send_push_notification(session_id: str, title: str) -> None:
    subscription = await get_push_subscription(session_id)
    if not subscription:
        return

    if not settings.next_public_vapid_key or not settings.vapid_private_key:
        logger.warning("Push notification skipped: missing VAPID keys")
        return

    payload = json.dumps(
        {
            "title": "Отчёт готов",
            "body": title,
            "url": f"/app/reports/{session_id}",
        },
        ensure_ascii=False,
    )
    vapid_claims = {"sub": "mailto:notifications@smart-report.local"}

    def _send() -> None:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims=vapid_claims,
        )

    try:
        await asyncio.to_thread(_send)
        logger.info(f"Push notification sent for session {session_id}")
    except WebPushException as exc:
        logger.warning(f"Push notification failed for session {session_id}: {exc}")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(f"Unexpected push notification error for session {session_id}: {exc}")
