"""v4 meta-analysis orchestrator — skeleton.

Three async entry-points map 1:1 to the three external-loop steps:

    1. generate_prompt  → calls Prompt Master (implemented, Track A)
    2. analyze          → calls Analyzer     (NotImplementedError — Track B fills)
    3. synthesize       → calls Synthesizer  (NotImplementedError — Track B fills)

Unlike v3's single run() that runs end-to-end, v4 is paused between each step
so the analyst can go paste prompts into external DR tools and upload results.
Session state between pauses lives in V4Session, held by V4SessionStore.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .events import EventEmitter, NullEmitter
from .models import (
    AnalysisOutput,
    FinalReport,
    ResearchPrompt,
    UploadedMarkdown,
    V4Session,
)
from .prompt_master import generate_research_prompt

if TYPE_CHECKING:  # pragma: no cover
    pass


class V4SessionStore:
    """In-memory store of V4Session objects, keyed by session_id.

    Process-local — acceptable for MVP (v3's /api/research uses the same pattern).
    A future persistence layer would replace this class with a DB-backed one.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, V4Session] = {}

    def create(self, session_id: str, raw_question: str) -> V4Session:
        if session_id in self._sessions:
            raise ValueError(f"session {session_id!r} already exists")
        s = V4Session(
            session_id=session_id,
            raw_question=raw_question,
            status="created",
            created_at=datetime.now(timezone.utc),
        )
        self._sessions[session_id] = s
        return s

    def get(self, session_id: str) -> V4Session:
        s = self._sessions.get(session_id)
        if s is None:
            raise KeyError(session_id)
        return s

    def update(self, session: V4Session) -> V4Session:
        self._sessions[session.session_id] = session
        return session

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def all(self) -> list[V4Session]:
        return list(self._sessions.values())


class V4Orchestrator:
    """Three-step orchestrator; each step is an independent async call."""

    def __init__(
        self,
        session_store: V4SessionStore,
        emitter: EventEmitter | None = None,
        *,
        log_dir: Path | None = None,
        mock: bool = False,
    ) -> None:
        self.store = session_store
        self.emitter = emitter or NullEmitter()
        self.log_dir = log_dir
        self.mock = mock

    # --- step 1: Prompt Master ---
    async def generate_prompt(
        self, session_id: str, question: str | None = None
    ) -> ResearchPrompt:
        session = self.store.get(session_id)
        q = question if question is not None else session.raw_question
        prompt = await generate_research_prompt(
            q,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
        )
        session.research_prompt = prompt
        session.status = "prompt_ready"
        self.store.update(session)
        return prompt

    # --- step 2: Analyzer (Track B) ---
    async def analyze(
        self,
        session_id: str,
        reports: list[UploadedMarkdown],
    ) -> AnalysisOutput:
        # Touching the session here so Track B starts with state already attached.
        session = self.store.get(session_id)
        if reports:
            session.source_reports = list(reports)
            session.status = "reports_uploaded"
            self.store.update(session)
        raise NotImplementedError(
            "v4_orchestrator.analyze is owned by Track B (smart_report/analyzer.py)"
        )

    # --- step 3: Synthesizer (Track B) ---
    async def synthesize(
        self,
        session_id: str,
        followup: list[UploadedMarkdown] | None = None,
    ) -> FinalReport:
        session = self.store.get(session_id)
        if followup:
            session.followup_reports = list(followup)
            session.status = "dobor_uploaded"
            self.store.update(session)
        raise NotImplementedError(
            "v4_orchestrator.synthesize is owned by Track B (smart_report/synthesizer.py)"
        )

    # --- cost accounting ---
    def _accumulate_cost(self, session: V4Session, llm_result_cost_rub: float) -> V4Session:
        """Add a single LLM-call cost to the session total.

        llm.py currently logs cost per call into runs/<ts>/llm_log.jsonl but does
        not expose a process-level meter. Track B or a follow-up should wire the
        real value in; for now this helper is the single place where that
        integration lands, so callers already talk to the right API.
        """
        if llm_result_cost_rub and llm_result_cost_rub > 0:
            session.total_cost_rub = round(session.total_cost_rub + llm_result_cost_rub, 4)
            self.store.update(session)
        return session
