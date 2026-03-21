from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from loguru import logger

from backend.schemas.knowledge_unit import KnowledgeUnit
from backend.schemas.quality import CitationStatus, CitationVerificationResult
from backend.schemas.research_result import ResearchResult

DB_PATH = Path("./data/facts.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS facts (
    id               TEXT PRIMARY KEY,
    content          TEXT NOT NULL,
    content_hash     TEXT UNIQUE NOT NULL,
    source_url       TEXT DEFAULT '',
    verified_at      TEXT NOT NULL,
    reliability_score REAL DEFAULT 0.8,
    topic_tags       TEXT DEFAULT '[]',
    session_id       TEXT DEFAULT ''
)
"""


class FactsStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path

    async def _init(self, conn: aiosqlite.Connection) -> None:
        await conn.execute(_CREATE_TABLE)
        await conn.commit()

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    async def save_verified_facts(
        self,
        research_results: list[ResearchResult],
        citation_verification: CitationVerificationResult,
        session_id: str,
        topic_tags: list[str] | None = None,
    ) -> int:
        """Persist only VERIFIED findings. Deduplicates via content MD5."""
        verified_urls: set[str] = {
            c.url
            for c in citation_verification.checks
            if c.status == CitationStatus.VERIFIED
        }
        verified_at = datetime.now(timezone.utc).isoformat()
        tags_json = json.dumps(topic_tags or [])
        saved = 0

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as conn:
            await self._init(conn)
            for result in research_results:
                source_url = next(
                    (s.url for s in result.sources if s.url in verified_urls), ""
                )
                reliability = next(
                    (
                        s.relevance_score
                        for s in result.sources
                        if s.url in verified_urls
                    ),
                    0.8,
                ) if verified_urls else 0.0

                for finding in result.findings:
                    content_hash = hashlib.md5(finding.encode()).hexdigest()
                    fact_id = f"fact_{content_hash[:16]}"
                    try:
                        cur = await conn.execute(
                            """
                            INSERT OR IGNORE INTO facts
                                (id, content, content_hash, source_url, verified_at,
                                 reliability_score, topic_tags, session_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                fact_id, finding, content_hash, source_url,
                                verified_at, reliability, tags_json, session_id,
                            ),
                        )
                        if cur.rowcount:
                            saved += 1
                    except Exception as exc:
                        logger.warning(f"Failed to insert fact {fact_id}: {exc}")

            await conn.commit()

        logger.info(f"FactsStore: saved {saved} verified facts for session {session_id}")
        return saved

    # ------------------------------------------------------------------
    # Public read API (returns KnowledgeUnit for backward compat)
    # ------------------------------------------------------------------

    async def get(self, fact_id: str) -> KnowledgeUnit | None:
        if not self._db_path.exists():
            return None
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM facts WHERE id = ?", (fact_id,)
            ) as cur:
                row = await cur.fetchone()
                return self._row_to_unit(dict(row)) if row else None

    async def search(self, query: str, category: str | None = None) -> list[KnowledgeUnit]:
        if not self._db_path.exists():
            return []
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM facts WHERE content LIKE ? LIMIT 50",
                (f"%{query}%",),
            ) as cur:
                rows = await cur.fetchall()
        return [self._row_to_unit(dict(r)) for r in rows]

    async def list_all(self) -> list[KnowledgeUnit]:
        if not self._db_path.exists():
            return []
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM facts ORDER BY verified_at DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [self._row_to_unit(dict(r)) for r in rows]

    async def get_by_session(self, session_id: str) -> list[KnowledgeUnit]:
        if not self._db_path.exists():
            return []
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM facts WHERE session_id = ?", (session_id,)
            ) as cur:
                rows = await cur.fetchall()
        return [self._row_to_unit(dict(r)) for r in rows]

    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_unit(row: dict) -> KnowledgeUnit:
        return KnowledgeUnit(
            id=row["id"],
            content=row["content"],
            source=row.get("source_url", ""),
            category="fact",
            confidence=row.get("reliability_score", 0.8),
            tags=json.loads(row.get("topic_tags", "[]")),
        )


facts_store = FactsStore()
