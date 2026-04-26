"""PostgreSQL-backed V4SessionStore.

Implements the same surface as `smart_report.v4_orchestrator.V4SessionStore`
(create / get / update / exists / all) but persists each session as a
JSONB row in a single `v4_sessions` table. Survives Railway container
restarts.

Schema deliberately minimal — one table, one JSONB column, no normalised
joins. Whenever the V4Session pydantic model changes, this layer keeps
working without migrations because the whole object goes in/out as JSON.
Trade-off: no per-field SQL queries (acceptable until we need analytics
across sessions, which is post-product-validation).

Selection: ``make_session_store()`` returns the Postgres-backed store when
``DATABASE_URL`` is set in env (Railway provides this for the linked
PostgreSQL service), else the in-memory dict store from v4_orchestrator
(the original MVP path, still useful for unit tests).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from .models import V4Session

log = logging.getLogger("smart_report.persistence")


# ---------------------------------------------------------------------------
# Postgres store
# ---------------------------------------------------------------------------


_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS v4_sessions (
    session_id TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class PgV4SessionStore:
    """Drop-in replacement for V4SessionStore backed by PostgreSQL.

    Uses psycopg (v3) sync API with a tiny connection pool. The orchestrator
    calls store methods from inside async handlers but the calls themselves
    are sync — wrapping in psycopg's threadpool keeps things simple and
    correct (no asyncpg event-loop interleaving).
    """

    def __init__(self, dsn: str) -> None:
        # Lazy import so importing this module never fails when psycopg
        # isn't installed (e.g. dev without the new requirement).
        import psycopg
        from psycopg_pool import ConnectionPool

        self._psycopg = psycopg
        self._pool = ConnectionPool(
            conninfo=dsn,
            min_size=1,
            max_size=8,
            kwargs={"autocommit": True},
        )
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(_TABLE_DDL)

    def create(self, session_id: str, raw_question: str) -> V4Session:
        if self.exists(session_id):
            raise ValueError(f"session {session_id!r} already exists")
        s = V4Session(
            session_id=session_id,
            raw_question=raw_question,
            status="created",
            created_at=datetime.now(timezone.utc),
        )
        self._upsert(s)
        return s

    def get(self, session_id: str) -> V4Session:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT payload FROM v4_sessions WHERE session_id = %s",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return V4Session.model_validate(row[0])

    def update(self, session: V4Session) -> V4Session:
        self._upsert(session)
        return session

    def exists(self, session_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM v4_sessions WHERE session_id = %s LIMIT 1",
                (session_id,),
            ).fetchone()
        return row is not None

    def all(self) -> list[V4Session]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT payload FROM v4_sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [V4Session.model_validate(r[0]) for r in rows]

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _upsert(self, session: V4Session) -> None:
        # `mode=json` serialises datetime → ISO string so JSONB ingest works.
        payload = session.model_dump(mode="json")
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO v4_sessions (session_id, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (session_id) DO UPDATE
                    SET payload = EXCLUDED.payload,
                        updated_at = NOW()
                """,
                (session.session_id, json.dumps(payload, ensure_ascii=False)),
            )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


_singleton_lock = threading.Lock()
_singleton_store: Optional[object] = None


def make_session_store():
    """Return the canonical session store for this process.

    - DATABASE_URL set → PgV4SessionStore (production on Railway)
    - DATABASE_URL absent → in-memory V4SessionStore (dev / tests)

    Caches a singleton so all callers share the same connection pool.
    """
    global _singleton_store
    with _singleton_lock:
        if _singleton_store is not None:
            return _singleton_store
        dsn = os.environ.get("DATABASE_URL", "").strip()
        if dsn:
            try:
                _singleton_store = PgV4SessionStore(dsn)
                log.info("v4 session store: PostgreSQL (DATABASE_URL set)")
            except Exception:
                log.exception("PostgreSQL store init failed — falling back to in-memory")
                from .v4_orchestrator import V4SessionStore
                _singleton_store = V4SessionStore()
        else:
            from .v4_orchestrator import V4SessionStore
            _singleton_store = V4SessionStore()
            log.info("v4 session store: in-memory (DATABASE_URL not set)")
    return _singleton_store
