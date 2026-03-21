from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import aiosqlite
from loguru import logger

from backend.schemas.research_result import Source

DB_PATH = Path("./data/sources.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sources (
    id               SERIAL PRIMARY KEY,
    url              TEXT UNIQUE NOT NULL,
    title            TEXT DEFAULT '',
    domain           TEXT DEFAULT '',
    crawled_at       TEXT NOT NULL,
    reliability_score REAL DEFAULT 0.5,
    topic_tags       TEXT DEFAULT '[]',
    usage_count      INTEGER DEFAULT 1
)
"""


class SourcesStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path

    async def _init(self, conn: aiosqlite.Connection) -> None:
        await conn.execute(_CREATE_TABLE)
        await conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def upsert_sources(
        self,
        sources: list[Source],
        topic_tags: list[str] | None = None,
    ) -> None:
        """Upsert sources; increment usage_count on conflict."""
        if not sources:
            return
        now = datetime.now(timezone.utc).isoformat()
        tags_json = json.dumps(topic_tags or [])

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as conn:
            await self._init(conn)
            for src in sources:
                domain = src.domain or _extract_domain(src.url)
                await conn.execute(
                    """
                    INSERT INTO sources (url, title, domain, crawled_at, reliability_score,
                                         topic_tags, usage_count)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(url) DO UPDATE SET
                        usage_count      = usage_count + 1,
                        crawled_at       = excluded.crawled_at,
                        reliability_score = MAX(reliability_score, excluded.reliability_score),
                        topic_tags       = excluded.topic_tags
                    """,
                    (src.url, src.title, domain, now, src.relevance_score, tags_json),
                )
            await conn.commit()
        logger.info(f"SourcesStore: upserted {len(sources)} sources")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def has_this_url_been_crawled_recently(
        self, url: str, max_age_days: int = 30
    ) -> bool:
        """True if url exists in DB and was crawled within max_age_days."""
        if not self._db_path.exists():
            return False
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max_age_days)
        ).isoformat()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute(
                "SELECT crawled_at FROM sources WHERE url = ?", (url,)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return False
        return row[0] >= cutoff

    async def get(self, url: str) -> Source | None:
        if not self._db_path.exists():
            return None
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM sources WHERE url = ?", (url,)
            ) as cur:
                row = await cur.fetchone()
        return self._row_to_source(dict(row)) if row else None

    async def search(self, query: str) -> list[Source]:
        if not self._db_path.exists():
            return []
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM sources WHERE title LIKE ? OR url LIKE ? LIMIT 50",
                (f"%{query}%", f"%{query}%"),
            ) as cur:
                rows = await cur.fetchall()
        results = [self._row_to_source(dict(r)) for r in rows]
        return sorted(results, key=lambda s: s.relevance_score, reverse=True)

    async def list_all(self) -> list[Source]:
        if not self._db_path.exists():
            return []
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM sources ORDER BY usage_count DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [self._row_to_source(dict(r)) for r in rows]

    async def top_sources(self, limit: int = 20) -> list[dict]:
        """Return raw rows ordered by usage_count for analytics."""
        if not self._db_path.exists():
            return []
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM sources ORDER BY usage_count DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_source(row: dict) -> Source:
        return Source(
            url=row["url"],
            title=row.get("title", ""),
            snippet="",
            domain=row.get("domain", ""),
            relevance_score=row.get("reliability_score", 0.5),
        )


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


sources_store = SourcesStore()
