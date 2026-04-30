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

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .analytic_depth import build_analytic_depth_plan
from .events import EventEmitter, NullEmitter
from .models import (
    AnalysisOutput,
    FinalReport,
    NormalizedReport,
    ResearchPrompt,
    UploadedMarkdown,
    V4Session,
)
from .analyzer import analyze_reports
from .bibliography import generate_bibliography
from .config import models_for_preference
from .data_audit import CoverageReport, audit_fact_coverage, build_retry_feedback
from .intake import normalize_all_reports
from .prompt_master import generate_research_prompt
from .domain_detector import QueryDomain, detect_query_domain
from .gap_detector import detect_gaps, gap_count_by_severity
from .synthesis_critic import ConsistencyReport, validate_consistency
from .synthesizer import full_report_text, synthesize_final_report
from .i18n import lint_output_language

if TYPE_CHECKING:  # pragma: no cover
    pass


# Track 3 (Language Lint) retry threshold — number of non-whitelisted Latin
# tokens above which the orchestrator retries the Synthesizer with a feedback
# pass. Live Acceptance Run 1 measured 100-310 warnings on realistic Russian
# RE reports because 5-20 mentions of international consultancies (JLL, CBRE,
# Knight Frank, Cushman & Wakefield, etc.) each emit several lint hits even
# when the brand itself is whitelisted (article fragments around the brand
# trip the Latin-token regex). Threshold of 20 made every such run pay 3×
# Synthesizer cost. 100 still catches the genuine "report half in English"
# bad case (which produces 1000+ warnings) while letting realistic
# Russian-language reports complete in one pass.
LINT_WARNING_RETRY_THRESHOLD = 100


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

    def monthly_spend_rub(self, email: str, days: int = 30) -> float:
        """In-memory equivalent of PgV4SessionStore.monthly_spend_rub —
        kept here so the cost-cap callsite is store-agnostic."""
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        cutoff = _dt.now(_tz.utc) - _td(days=days)
        total = 0.0
        for s in self._sessions.values():
            if getattr(s, "user_email", None) != email:
                continue
            created = s.created_at
            if hasattr(created, "tzinfo") and created.tzinfo is None:
                created = created.replace(tzinfo=_tz.utc)
            if created < cutoff:
                continue
            total += float(s.total_cost_rub or 0.0)
        return total

    def delete(self, session_id: str) -> None:
        """Remove session if present. No-op if missing — idempotent."""
        self._sessions.pop(session_id, None)


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
        self, session_id: str, question: str | None = None, model_preference: str | None = None
    ) -> ResearchPrompt:
        session = self.store.get(session_id)
        q = question if question is not None else session.raw_question
        models = models_for_preference(model_preference)
        prompt, cost_rub = await generate_research_prompt(
            q,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
            model=models["prompt_master"],
        )
        session.research_prompt = prompt
        session.status = "prompt_ready"
        await asyncio.to_thread(self.store.update, session)
        session = await self._accumulate_cost(session, cost_rub)
        return prompt

    # --- step 2: Analyzer ---
    async def analyze(
        self,
        session_id: str,
        reports: list[UploadedMarkdown] | None = None,
        model_preference: str | None = None,
    ) -> AnalysisOutput:
        session = self.store.get(session_id)
        if reports:
            session.source_reports = list(reports)
        if not session.source_reports:
            raise ValueError(
                f"session {session_id}: no source_reports to analyze — "
                "upload reports first"
            )
        session.status = "reports_uploaded"
        await asyncio.to_thread(self.store.update, session)

        print(
            f"[orch-analyze] session={session_id} starting; sources={len(session.source_reports)} "
            f"(normalize → analyzer LLM → followup_prompt)",
            flush=True,
        )
        initial_depth = build_analytic_depth_plan(session.raw_question)
        self.emitter.emit(
            "analytic_depth",
            (
                "Initial investigation map prepared: "
                f"{len(initial_depth.root.children)} branches, "
                f"{len(initial_depth.benchmark_questions)} benchmark questions."
            ),
            data={
                "stage": "initial_plan",
                "domain_hint": initial_depth.domain_hint,
                "branches": len(initial_depth.root.children),
                "benchmark_questions": len(initial_depth.benchmark_questions),
                "methods": initial_depth.root.methods,
            },
        )

        # v4.5: normalize each source report (extract citations + numeric/qualitative facts)
        research_prompt_text = (
            session.research_prompt.full_prompt if session.research_prompt else session.raw_question
        )
        normalized_reports = await normalize_all_reports(
            session.source_reports,
            research_prompt=research_prompt_text,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
        )
        session.normalized_reports = normalized_reports

        models = models_for_preference(model_preference)
        analysis, cost_rub = await analyze_reports(
            question=session.raw_question,
            research_prompt=session.research_prompt,
            source_reports=session.source_reports,
            normalized_reports=normalized_reports,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
            model=models["analyzer"],
        )
        depth_plan = build_analytic_depth_plan(session.raw_question, analysis=analysis)
        self.emitter.emit(
            "analytic_depth",
            (
                "Analytical depth map updated: "
                f"{len(depth_plan.hypotheses)} hypotheses, "
                f"{len(depth_plan.evidence_probes)} evidence probes, "
                f"{len(depth_plan.research_leads)} research leads."
            ),
            data={
                "stage": "post_analysis_plan",
                "domain_hint": depth_plan.domain_hint,
                "branches": len(depth_plan.root.children),
                "hypotheses": len(depth_plan.hypotheses),
                "evidence_probes": len(depth_plan.evidence_probes),
                "research_leads": len(depth_plan.research_leads),
                "disconfirming_probes": sum(
                    1 for probe in depth_plan.evidence_probes if probe.disconfirming
                ),
                "must_leads": sum(
                    1 for lead in depth_plan.research_leads if lead.priority == "must"
                ),
                "lead_kinds": [lead.kind for lead in depth_plan.research_leads[:6]],
            },
        )
        print(
            f"[orch-analyze] session={session_id} analyze_reports returned; "
            f"writing session.analysis (PG)",
            flush=True,
        )
        session.analysis = analysis
        session.status = "analyzed"
        await asyncio.to_thread(self.store.update, session)
        print(
            f"[orch-analyze] session={session_id} store.update OK; "
            f"accumulating cost ₽{cost_rub:.2f}",
            flush=True,
        )
        session = await self._accumulate_cost(session, cost_rub)
        print(
            f"[orch-analyze] session={session_id} DONE total_cost_rub={session.total_cost_rub} "
            f"returning to client (status=analyzed)",
            flush=True,
        )
        return analysis

    # --- step 3: Synthesizer ---
    async def synthesize(
        self,
        session_id: str,
        followup: list[UploadedMarkdown] | None = None,
        model_preference: str | None = None,
    ) -> FinalReport:
        session = self.store.get(session_id)
        if followup:
            session.followup_reports = list(followup)
            session.status = "dobor_uploaded"
            await asyncio.to_thread(self.store.update, session)
        if session.analysis is None:
            raise ValueError(
                f"session {session_id}: analyze must run before synthesize"
            )

        print(f"[orch-synth] session={session_id} 3a: first synthesis pass starting", flush=True)
        # Step 3a: first synthesis pass
        models = models_for_preference(model_preference)
        final, cost_rub = await synthesize_final_report(
            session,
            emitter=self.emitter,
            log_dir=self.log_dir,
            mock=self.mock,
            model=models["synthesizer"],
        )
        session = await self._accumulate_cost(session, cost_rub)

        # Step 3b: bibliography post-processing
        final, _ = generate_bibliography(final)

        # COMMIT the first-pass result IMMEDIATELY so downstream retry failures
        # (coverage/consistency/language) don't lose the report we already paid for.
        # Any subsequent retries mutate `final` in-place and re-commit.
        session.final_report = final
        session.status = "synthesized"
        await asyncio.to_thread(self.store.update, session)
        self.emitter.emit(
            "bibliography",
            "Bibliography generated",
            data={
                "source_count": final.source_count,
                "citation_coverage": final.citation_coverage,
            },
        )

        print(f"[orch-synth] session={session_id} 3a done, 3c coverage audit", flush=True)
        # Step 3c: data coverage audit
        coverage_report: CoverageReport = audit_fact_coverage(session.analysis, final)
        print(
            f"[orch-synth] session={session_id} coverage verdict={coverage_report.verdict} "
            f"facts={coverage_report.facts_in_final}/{coverage_report.high_relevance_total} "
            f"({coverage_report.coverage_pct:.0f}%)",
            flush=True,
        )
        self.emitter.emit(
            "data_audit",
            f"Coverage audit: {coverage_report.verdict}",
            data={
                "coverage_pct": coverage_report.coverage_pct,
                "facts_in_final": coverage_report.facts_in_final,
                "high_relevance_total": coverage_report.high_relevance_total,
                "verdict": coverage_report.verdict,
            },
        )

        # Step 3d: one retry on coverage failure (best-effort — don't nuke first pass)
        if coverage_report.verdict in ("poor", "critical_failure") and not self.mock:
            print(f"[orch-synth] session={session_id} 3d coverage retry triggered", flush=True)
            feedback = build_retry_feedback(coverage_report)
            if feedback and session.analysis.high_relevance_facts:
                self.emitter.emit(
                    "synthesizer",
                    "Coverage below target — retrying with feedback",
                    data={"verdict": coverage_report.verdict},
                )
                session.analysis.quality_notes = (
                    (session.analysis.quality_notes or "") + "\n\n" + feedback
                )
                try:
                    final_retry, cost_rub_retry = await synthesize_final_report(
                        session,
                        emitter=self.emitter,
                        log_dir=self.log_dir,
                        mock=self.mock,
                        model=models["synthesizer"],
                    )
                    session = await self._accumulate_cost(session, cost_rub_retry)
                    final_retry, _ = generate_bibliography(final_retry)
                    coverage_report = audit_fact_coverage(session.analysis, final_retry)
                    final = final_retry
                    session.final_report = final
                    await asyncio.to_thread(self.store.update, session)
                except Exception as e:
                    self.emitter.emit("synthesizer", f"Coverage retry failed: {e!r} — keeping first pass", data={})

        final.metadata["coverage_audit"] = {
            "coverage_pct": coverage_report.coverage_pct,
            "facts_in_final": coverage_report.facts_in_final,
            "high_relevance_total": coverage_report.high_relevance_total,
            "verdict": coverage_report.verdict,
            "detail": coverage_report.detail,
        }
        await asyncio.to_thread(self.store.update, session)

        print(f"[orch-synth] session={session_id} 3e consistency critic starting", flush=True)
        # Step 3e: Consistency Critic loop (max 1 retry, best-effort)
        try:
            consistency = await validate_consistency(
                final,
                emitter=self.emitter,
                log_dir=self.log_dir,
                mock=self.mock,
                model=models["critic"],
            )
            print(f"[orch-synth] session={session_id} consistency verdict={consistency.overall_verdict}", flush=True)
            if consistency.overall_verdict == "critical_failure":
                print(f"[orch-synth] session={session_id} consistency retry triggered", flush=True)
                try:
                    final, cost_rub_c = await synthesize_final_report(
                        session,
                        emitter=self.emitter,
                        log_dir=self.log_dir,
                        mock=self.mock,
                        consistency_feedback=consistency,
                        model=models["synthesizer"],
                    )
                    session = await self._accumulate_cost(session, cost_rub_c)
                    final, _ = generate_bibliography(final)
                    consistency = await validate_consistency(
                        final,
                        emitter=self.emitter,
                        log_dir=self.log_dir,
                        mock=self.mock,
                        model=models["critic"],
                    )
                    session.final_report = final
                    await asyncio.to_thread(self.store.update, session)
                except Exception as e:
                    self.emitter.emit("synthesizer", f"Consistency retry failed: {e!r} — keeping current", data={})
            final.metadata["consistency_check"] = consistency.model_dump()
        except Exception as e:
            self.emitter.emit("critic", f"Consistency check failed: {e!r} — skipping", data={})
            final.metadata["consistency_check"] = {"error": str(e), "overall_verdict": "skipped"}
        await asyncio.to_thread(self.store.update, session)

        # Step 3f: Language lint (Track 3) — retry above LINT_WARNING_RETRY_THRESHOLD, best-effort
        lint_warnings = lint_output_language(full_report_text(final))
        print(
            f"[orch-synth] session={session_id} 3f language lint: {len(lint_warnings)} warnings "
            f"(threshold={LINT_WARNING_RETRY_THRESHOLD})",
            flush=True,
        )
        if len(lint_warnings) > LINT_WARNING_RETRY_THRESHOLD and not self.mock:
            print(f"[orch-synth] session={session_id} 3f language retry triggered", flush=True)
            self.emitter.emit(
                "orchestrator",
                f"Language lint: {len(lint_warnings)} warnings — retrying Synthesizer",
                data={"warnings_count": len(lint_warnings)},
            )
            try:
                final_l, cost_rub_l = await synthesize_final_report(
                    session,
                    emitter=self.emitter,
                    log_dir=self.log_dir,
                    mock=self.mock,
                    language_feedback=[w.model_dump() for w in lint_warnings],
                    model=models["synthesizer"],
                )
                session = await self._accumulate_cost(session, cost_rub_l)
                final_l, _ = generate_bibliography(final_l)
                lint_warnings = lint_output_language(full_report_text(final_l))
                final = final_l
                session.final_report = final
                await asyncio.to_thread(self.store.update, session)
            except Exception as e:
                self.emitter.emit("orchestrator", f"Language retry failed: {e!r} — keeping current", data={})

        final.metadata["language_lint"] = {
            "warnings_count": len(lint_warnings),
            "warnings": [w.model_dump() for w in lint_warnings[:20]],
        }

        # Step 3g (Phase 2 Step 2.3 — C6 degraded): per-sub-question
        # evidence-adequacy detection. Runs AFTER all retry paths (Coverage,
        # Critic, Lint) so the gap metadata + confidence_note prefix land
        # on whatever final the orchestrator is about to return — earlier
        # placement was clobbered by retry chains that replace `final`.
        # Fires only when the Step 2.2 LLM planner populated sub_questions;
        # the Step 2.1 RU RE template path uses inline SubQuery dicts
        # (out of scope for the C6 detector).
        #
        # Phase 3 Step 3.2: detect query domain UNCONDITIONALLY for
        # metadata transparency (so analysts can see which registry the
        # query was routed to even when the template path skipped gap
        # detection). The actual gap detection still gates on
        # sub_questions presence.
        query_domain = detect_query_domain(session.raw_question)
        final.metadata["query_domain"] = query_domain.value
        if session.research_prompt and session.research_prompt.sub_questions:
            await _attach_evidence_gaps(
                final,
                session.research_prompt.sub_questions,
                session.analysis,
                emitter=self.emitter,
                query_domain=query_domain,
            )

        session.final_report = final
        session.status = "synthesized"
        await asyncio.to_thread(self.store.update, session)
        print(
            f"[orch-synth] session={session_id} DONE total_cost_rub={session.total_cost_rub} "
            f"sources={len(final.all_sources)} status=synthesized",
            flush=True,
        )
        return final

    # --- gap detection helper exposed at module level for cleaner testing ---
    # See _attach_evidence_gaps below.

    # --- cost accounting ---
    async def _accumulate_cost(self, session: V4Session, llm_result_cost_rub: float) -> V4Session:
        """Add a single LLM-call cost to the session total.

        Async because the underlying store.update is a sync DB write —
        wrapping in asyncio.to_thread keeps the event loop free for
        other handlers (events long-poll, auto-dr-status polls) while
        the JSONB upsert is in flight. Previously synthesize/analyze's
        ~12 store.update calls each blocked the loop for 200-500ms,
        starving concurrent requests.
        """
        if llm_result_cost_rub and llm_result_cost_rub > 0:
            session.total_cost_rub = round(session.total_cost_rub + llm_result_cost_rub, 4)
            await asyncio.to_thread(self.store.update, session)
        return session


# ---------------------------------------------------------------------------
# Phase 2 Step 2.3 — Gap detection helper
# ---------------------------------------------------------------------------


_SEVERITY_LABEL_RU = {
    "critical": "Критично",
    "moderate": "Умеренно",
    "minor": "Незначительно",
}


def _format_gap_warning_for_confidence_note(gaps: list) -> str:
    """Render gaps as a Cyrillic warning for executive_summary.confidence_note.

    Same anti-lint-retry discipline as Step 1.2: zero Latin-script
    sentinels in the visible string (paid lesson 7.2). The
    machine-readable list — including sub_question ids and API endpoint
    references — lives in metadata["evidence_gaps"]; this is the
    human-facing summary, kept in pure Cyrillic so it never trips the
    language linter and never costs a Track 3 retry.
    """
    if not gaps:
        return ""
    counts = gap_count_by_severity(gaps)
    header = (
        f"⚠ Пробелы в доказательной базе: найдено {len(gaps)} под-вопросов "
        f"с недостаточным покрытием (критичных: {counts['critical']}, "
        f"умеренных: {counts['moderate']}, незначительных: {counts['minor']})."
    )
    bullets = []
    for i, g in enumerate(gaps[:8], start=1):  # cap to keep note readable
        label = _SEVERITY_LABEL_RU.get(g.severity, g.severity)
        sq_text = g.sub_question_text
        if len(sq_text) > 120:
            sq_text = sq_text[:117] + "…"
        # Use Cyrillic ordinal "Под-вопрос N:" so the visible string
        # carries no Latin tokens; raw sub_question_id stays in metadata.
        bullets.append(f"• [{label}] Под-вопрос {i}: {sq_text}")
    if len(gaps) > 8:
        bullets.append(f"…и ещё {len(gaps) - 8} под-вопросов с пробелами.")
    suffix = (
        "Аналитику стоит прогнать целевые исследовательские запросы по "
        "этим темам и повторно загрузить новые отчёты в систему. "
        "Целевые промпты доступны через системный эндпоинт проверки "
        "пробелов (см. метаданные отчёта)."
    )
    return header + "\n\n" + "\n".join(bullets) + "\n\n" + suffix


async def _attach_evidence_gaps(
    final,
    sub_questions: list,
    analysis,
    *,
    emitter,
    query_domain: QueryDomain = QueryDomain.RU_REAL_ESTATE,
) -> None:
    """Run gap detection and surface results on *final* in place.

    - final.metadata["evidence_gaps"]: list[dict] for downstream readers
    - final.metadata["gap_count_by_severity"]: tally
    - final.executive_summary.confidence_note: prefixed Cyrillic warning
      (preserves any existing note from Step 1.2 LOW_EVIDENCE_QUALITY
      or LLM-generated text)
    """
    gaps = await detect_gaps(sub_questions, analysis, query_domain=query_domain)
    final.metadata["evidence_gaps"] = [g.model_dump() for g in gaps]
    final.metadata["gap_count_by_severity"] = gap_count_by_severity(gaps)
    emitter.emit(
        "gap_detector",
        f"Gap detection: {len(gaps)} gaps across {len(sub_questions)} sub-questions",
        data=final.metadata["gap_count_by_severity"],
    )
    if gaps:
        warning = _format_gap_warning_for_confidence_note(gaps)
        prior_note = final.executive_summary.confidence_note
        merged_note = warning if not prior_note else f"{warning}\n\n{prior_note}"
        final.executive_summary = final.executive_summary.model_copy(
            update={"confidence_note": merged_note}
        )
