"""Live acceptance tests for v4.5 Phase 1 + Phase 2 Step 2.1.

Three tests run end-to-end through the v4 orchestrator IN-PROCESS
(no FastAPI server needed). Each saves its full final report to
``tests/fixtures/live_runs/2026-04-25_test{N}_*.json`` for inspection
and future regression material.

Usage:
    python -m scripts.live_acceptance_run test1
    python -m scripts.live_acceptance_run test2
    python -m scripts.live_acceptance_run test3

Models:
    test1, test2 — Haiku 4.5 across all stages (cheap)
    test3        — Sonnet 4.6 across all stages (full v4 cycle)

Costs are tracked in RUB by the pipeline and converted to USD at
75.4 RUB/USD (rate captured 2026-04-25). Hard cap on test3: $5.00.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Diagnostic: capture HTTP error response bodies so a 400 from OpenRouter
# tells us WHY (token limits, schema, etc.) rather than just dying with
# "Client error '400 Bad Request'". Patches httpx.Response globally for
# this process — fine in a one-off script.
import httpx as _httpx
_orig_raise = _httpx.Response.raise_for_status
def _verbose_raise(self):
    if self.is_error:
        try:
            body = self.text[:1500]
        except Exception:
            body = "<unreadable>"
        print(f"\n*** HTTP {self.status_code} from {self.request.url} ***", flush=True)
        print(f"*** Response body (truncated): {body}\n", flush=True)
    return _orig_raise(self)
_httpx.Response.raise_for_status = _verbose_raise

from smart_report.evidence_grades import (
    count_evidence_grades,
    evidence_grade_distribution,
    has_grade_variance,
)
from smart_report.models import ResearchPrompt, UploadedMarkdown, V4Session
from smart_report import v4_orchestrator as v4_module
from smart_report.v4_orchestrator import V4Orchestrator, V4SessionStore

USD_RUB_RATE = 75.4
TEST3_HARD_CAP_USD = 5.00
HAIKU = "anthropic/claude-haiku-4.5"
SONNET = "anthropic/claude-sonnet-4.6"

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_AMENITIES = sorted((REPO_ROOT / "runs/night_upgrade/fixtures").glob("*.md"))
OUT_DIR = REPO_ROOT / "tests/fixtures/live_runs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _all_stages(model: str, *, synth_override: str | None = None) -> dict[str, str]:
    """Map every pipeline stage to *model*.

    *synth_override* swaps just the synthesizer (and consistency critic
    that gates it) — useful when intake+analyze fit the cheap-tier
    context but synthesize bloats past it (v4.5 dual-injection bug).
    """
    s = synth_override or model
    return {"prompt_master": model, "analyzer": model, "synthesizer": s, "critic": s}


def _detect_tool(filename: str):
    name = filename.lower()
    if "perplexity" in name or "pplx" in name:
        return "perplexity"
    if "openai" in name or "chatgpt" in name or "deep-research" in name:
        return "openai_dr"
    if "claude" in name:
        return "claude"
    return "other"


def _load_amenities_uploads(*, subset: list[str] | None = None) -> list[UploadedMarkdown]:
    """Load fixture markdown files. ``subset`` filters by basename match.

    The full 4-file fixture set produces a synthesizer prompt of ~400k
    tokens (intake's dual-injection bug — analyzer dump + facts inventory
    overlap). On Haiku 4.5 (200k context) this 400s. Pass subset=[...]
    to restrict to a smaller set on cheap-tier tests.
    """
    paths = FIXTURES_AMENITIES
    if subset is not None:
        wanted = set(subset)
        paths = [p for p in paths if p.name in wanted]
        if not paths:
            raise ValueError(f"subset {subset!r} matched no fixtures in {FIXTURES_AMENITIES!r}")
    uploads: list[UploadedMarkdown] = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        uploads.append(
            UploadedMarkdown(
                filename=p.name,
                content=text,
                detected_tool=_detect_tool(p.name),
                word_count=len(text.split()),
            )
        )
    return uploads


# ---------------------------------------------------------------------------
# Synthetic out-of-domain markdown for Test 2
# ---------------------------------------------------------------------------
# Goal: a realistic-looking DR report whose source URLs are entirely
# outside AUTHORITATIVE_RU_RE_DOMAINS so the C3 heuristic must fire.
# We avoid any rosstat/minstroy/ДОМ.РФ/ЕРЗ/JLL/CBRE/etc. to keep the
# signal clean; sources are GitHub, vendor docs, and Medium-style blogs.

LLM_OBSERVABILITY_REPORT = """# LLM Observability platforms — Langfuse vs LangSmith vs Helicone

## Summary

Three platforms dominate the LLM observability space for enterprise teams:
Langfuse (open-source, OTEL-native), LangSmith (LangChain-managed, hosted),
and Helicone (proxy-based, fastest integration).

## Langfuse

Langfuse positions itself as the OSS choice. The project is on GitHub at
https://github.com/langfuse/langfuse with 6.5k stars as of October 2025.
Self-hosting documentation lives at https://langfuse.com/docs/deployment.
The pricing page at https://langfuse.com/pricing lists $49/month for the
hosted Pro tier with 100k observations included.

Strengths according to https://medium.com/@anyscale-engineer/langfuse-review-2025
include OpenTelemetry compatibility and the ability to attach arbitrary
metadata to traces. A blog comparison at https://www.helicone.ai/blog/langfuse-vs-helicone
notes weaker built-in dashboards versus competitors.

## LangSmith

LangSmith is the managed observability layer from the LangChain team.
Pricing at https://www.langchain.com/pricing starts at $39/seat/month for
the Plus tier. The product overview at https://docs.smith.langchain.com/
emphasizes the tight LangChain SDK integration.

A teardown at https://medium.com/@dev-blog/langsmith-deep-dive notes the
proprietary trace format limits portability — exporting to other tools
requires custom adapters.

## Helicone

Helicone takes a proxy-based approach: requests route through their gateway
which captures observability without SDK changes. The pricing model on
https://www.helicone.ai/pricing starts free for under 100k requests/month
and scales to $50/month for the Pro tier with 1M requests.

A G2 review at https://www.g2.com/products/helicone/reviews highlights the
fastest setup time (under 5 minutes) but flags weaker analytics depth.

## Recommendation

For enterprise teams needing maximum control: Langfuse self-hosted.
For LangChain-heavy stacks: LangSmith. For minimum-setup observability:
Helicone proxy mode.

## Sources

1. https://github.com/langfuse/langfuse
2. https://langfuse.com/docs/deployment
3. https://langfuse.com/pricing
4. https://medium.com/@anyscale-engineer/langfuse-review-2025
5. https://www.helicone.ai/blog/langfuse-vs-helicone
6. https://www.langchain.com/pricing
7. https://docs.smith.langchain.com/
8. https://medium.com/@dev-blog/langsmith-deep-dive
9. https://www.helicone.ai/pricing
10. https://www.g2.com/products/helicone/reviews
"""


def _llm_obs_uploads() -> list[UploadedMarkdown]:
    text = LLM_OBSERVABILITY_REPORT
    return [
        UploadedMarkdown(
            filename="llm_observability_dr_report.md",
            content=text,
            detected_tool="other",
            word_count=len(text.split()),
        )
    ]


# ---------------------------------------------------------------------------
# In-process v4 cycle harness
# ---------------------------------------------------------------------------


CHECKPOINT_DIR = REPO_ROOT / "runs/live_acceptance_checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def _checkpoint_path(name: str, model: str) -> Path:
    safe_model = model.replace("/", "_")
    return CHECKPOINT_DIR / f"{TODAY}_{name}_{safe_model}_after_analyze.json"


def _save_checkpoint(name: str, model: str, session: V4Session) -> None:
    p = _checkpoint_path(name, model)
    payload = {
        "session_id": session.session_id,
        "raw_question": session.raw_question,
        "research_prompt": session.research_prompt.model_dump() if session.research_prompt else None,
        "source_reports": [r.model_dump() for r in session.source_reports],
        "analysis": session.analysis.model_dump() if session.analysis else None,
        "normalized_reports": [n.model_dump() for n in session.normalized_reports],
        "total_cost_rub_so_far": session.total_cost_rub,
        "created_at": session.created_at.isoformat(),
        "status": session.status,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"  [checkpoint] saved {p}")


def _load_checkpoint(name: str, model: str) -> V4Session | None:
    from smart_report.models import AnalysisOutput, NormalizedReport
    from datetime import datetime as _dt
    p = _checkpoint_path(name, model)
    if not p.exists():
        return None
    payload = json.loads(p.read_text(encoding="utf-8"))
    sess = V4Session(
        session_id=payload["session_id"],
        raw_question=payload["raw_question"],
        research_prompt=ResearchPrompt(**payload["research_prompt"]) if payload["research_prompt"] else None,
        source_reports=[UploadedMarkdown(**r) for r in payload["source_reports"]],
        analysis=AnalysisOutput(**payload["analysis"]) if payload["analysis"] else None,
        normalized_reports=[NormalizedReport(**n) for n in payload["normalized_reports"]],
        status=payload["status"],
        created_at=_dt.fromisoformat(payload["created_at"]),
        total_cost_rub=payload["total_cost_rub_so_far"],
    )
    print(f"  [checkpoint] loaded {p} (skipping intake+analyze, cost so far={sess.total_cost_rub:.2f} RUB)")
    return sess


async def _run_cycle(
    *,
    question: str,
    uploads: list[UploadedMarkdown],
    model: str,
    run_prompt_master: bool,
    checkpoint_name: str | None = None,
    synth_override: str | None = None,
) -> tuple[V4Session, list[dict]]:
    """Run a v4 cycle end-to-end against the live LLM with *model* on every stage.

    When ``run_prompt_master`` is False, we inject a stub ResearchPrompt to
    skip that LLM call (saves cost on Tests 1+2 where the PM step is not
    being measured).

    If ``checkpoint_name`` is set and a post-analyze checkpoint exists for
    that (name, model), intake+analyzer are skipped and the saved state is
    loaded — so a synthesize-stage failure can be diagnosed without paying
    for upstream stages again.
    """
    store = V4SessionStore()

    captured_events: list[dict] = []

    class _ListEmitter:
        def emit(self, phase, message, *, data=None):
            captured_events.append(
                {"phase": phase, "message": message, "data": data}
            )
            print(f"  [{phase}] {message}")

    orch = V4Orchestrator(store, mock=False, emitter=_ListEmitter())

    stages_dict = _all_stages(model, synth_override=synth_override)
    print(f"  [models] {stages_dict}")
    with patch.object(v4_module, "models_for_preference", lambda pref: stages_dict):
        cached = _load_checkpoint(checkpoint_name, model) if checkpoint_name else None
        if cached is not None:
            store._sessions[cached.session_id] = cached
            sid = cached.session_id
        else:
            sid = uuid.uuid4().hex[:12]
            store.create(session_id=sid, raw_question=question)
            if run_prompt_master:
                await orch.generate_prompt(sid)
            else:
                sess = store.get(sid)
                sess.research_prompt = ResearchPrompt(
                    full_prompt=f"[stub PM skipped] Original question: {question}",
                    reasoning="stub",
                    expected_structure=[],
                    key_entities=[],
                    tips_for_search="",
                )
                sess.status = "prompt_ready"
                store.update(sess)

            sess = store.get(sid)
            sess.source_reports = uploads
            sess.status = "reports_uploaded"
            store.update(sess)

            await orch.analyze(sid)
            if checkpoint_name:
                _save_checkpoint(checkpoint_name, model, store.get(sid))

        await orch.synthesize(sid)

    return store.get(sid), captured_events


def _save_run(name: str, session: V4Session, events: list[dict], extras: dict) -> Path:
    out_path = OUT_DIR / f"{TODAY}_{name}.json"
    payload = {
        "test_name": name,
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_question": session.raw_question,
        "research_prompt": (
            session.research_prompt.model_dump() if session.research_prompt else None
        ),
        "analysis": session.analysis.model_dump() if session.analysis else None,
        "final_report": session.final_report.model_dump() if session.final_report else None,
        "total_cost_rub": session.total_cost_rub,
        "total_cost_usd_at_75_4": round(session.total_cost_rub / USD_RUB_RATE, 4),
        "events": events,
        "extras": extras,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# Acceptance checks
# ---------------------------------------------------------------------------


def _evaluate_test1(session: V4Session) -> dict:
    final = session.final_report
    distribution = evidence_grade_distribution(final)
    distinct = sum(1 for v in distribution.values() if v > 0)
    total_tags = sum(distribution.values())
    cost_usd = session.total_cost_rub / USD_RUB_RATE

    # Sample claims for qualitative review
    samples = []
    text_blocks = (
        [final.main_synthesis]
        + final.executive_summary.top_findings
        + [c.body for c in final.callouts]
    )
    import re
    grade_re = re.compile(r"\[(STRONG|MODERATE|WEAK|SPECULATIVE)\][^\.]+\.")
    for block in text_blocks:
        if not block:
            continue
        for m in grade_re.finditer(block):
            samples.append(m.group(0))
            if len(samples) >= 3:
                break
        if len(samples) >= 3:
            break

    pass_cost = cost_usd <= 0.60
    pass_count = total_tags >= 6
    pass_variance = distinct >= 2

    verdict = "PASS" if (pass_cost and pass_count and pass_variance) else "FAIL"
    if verdict == "FAIL" and pass_cost and pass_count and distinct == 1:
        verdict = "DEGRADED"

    return {
        "verdict": verdict,
        "cost_usd": round(cost_usd, 4),
        "cost_rub": round(session.total_cost_rub, 2),
        "evidence_grade_distribution": distribution,
        "distinct_grades": distinct,
        "total_tags": total_tags,
        "sample_claims": samples,
        "pass_cost_<=0.60": pass_cost,
        "pass_count_>=6": pass_count,
        "pass_variance_>=2": pass_variance,
    }


def _evaluate_test2(session: V4Session) -> dict:
    final = session.final_report
    cost_usd = session.total_cost_rub / USD_RUB_RATE
    quality = final.metadata.get("evidence_quality")
    warning = final.metadata.get("evidence_warning", "")
    confidence_note = final.executive_summary.confidence_note

    # Sentinel must NEVER appear in visible text — that's the lint retry trap
    visible_blocks = (
        final.main_synthesis,
        final.consensus_section,
        final.conflicts_section,
        final.gaps_filled_section,
        " ".join(final.executive_summary.top_findings),
        " ".join(c.body for c in final.callouts),
        " ".join(qa.answer for qa in final.qa_section),
    )
    sentinel_in_visible = any(
        "LOW_EVIDENCE_QUALITY" in (b or "") for b in visible_blocks
    )

    domains = [s.url for s in final.all_sources if s.url]

    pass_quality_flag = quality == "LOW_EVIDENCE_QUALITY"
    pass_warning_in_note = (
        "Низкое качество источников" in confidence_note
        or "вторичные источники" in confidence_note
    )
    pass_no_sentinel_visible = not sentinel_in_visible

    verdict = "PASS"
    if not pass_quality_flag:
        verdict = "FAIL"
    elif not pass_no_sentinel_visible:
        verdict = "FAIL"  # critical regression on principle #3
    elif not pass_warning_in_note:
        verdict = "DEGRADED"

    return {
        "verdict": verdict,
        "cost_usd": round(cost_usd, 4),
        "cost_rub": round(session.total_cost_rub, 2),
        "evidence_quality_metadata": quality,
        "evidence_warning_excerpt": warning[:200] if warning else "",
        "confidence_note_excerpt": confidence_note[:300],
        "all_source_urls": domains,
        "pass_quality_flag_LOW": pass_quality_flag,
        "pass_warning_cyrillic": pass_warning_in_note,
        "pass_no_sentinel_in_visible": pass_no_sentinel_visible,
    }


def _evaluate_test3(session: V4Session) -> dict:
    final = session.final_report
    pm = session.research_prompt
    cost_usd = session.total_cost_rub / USD_RUB_RATE

    # Decomposition guidance presence in PM output
    pm_text = pm.full_prompt if pm else ""
    sub_query_ids = ("macro_context", "regulatory_environment", "market_data", "developer_behavior")
    sub_queries_present = [sid for sid in sub_query_ids if sid in pm_text]

    # Evidence-grade variance
    distribution = evidence_grade_distribution(final)
    distinct = sum(1 for v in distribution.values() if v > 0)

    # LOW_EVIDENCE_QUALITY should NOT fire on a quality fixture set
    quality = final.metadata.get("evidence_quality")

    pass_cost = cost_usd <= 3.50
    pass_pm_decomposition = len(sub_queries_present) == 4
    pass_variance = distinct >= 2
    pass_quality_ok = quality == "OK"

    verdict = "PASS" if all([pass_cost, pass_pm_decomposition, pass_variance, pass_quality_ok]) else "FAIL"

    return {
        "verdict": verdict,
        "cost_usd": round(cost_usd, 4),
        "cost_rub": round(session.total_cost_rub, 2),
        "sub_queries_in_pm": sub_queries_present,
        "evidence_grade_distribution": distribution,
        "distinct_grades": distinct,
        "evidence_quality_metadata": quality,
        "source_count": len(final.all_sources),
        "pass_cost_<=3.50": pass_cost,
        "pass_pm_decomposition_4_4": pass_pm_decomposition,
        "pass_variance_>=2": pass_variance,
        "pass_quality_OK": pass_quality_ok,
    }


# ---------------------------------------------------------------------------
# Test entry points
# ---------------------------------------------------------------------------


async def test1():
    print("=" * 60)
    print("TEST 1 — C7 evidence-grade variance (Haiku 4.5, ~$1-1.5)")
    print("=" * 60)
    question = "Какие факторы повлияют на спрос на жильё бизнес-класса в Москве в 2026-2027?"
    # Hybrid model strategy: intake+analyzer on Haiku 4.5 (cheap, fits
    # 200k), synthesizer on Sonnet 4.6 (1M context). Reason: v4.5
    # _build_user_message has a dual-injection bug — analyzer.model_dump()
    # AND _build_facts_section both carry high_relevance_facts, blowing
    # the prompt to ~280k+ tokens even on a 2-fixture subset, which
    # overflows Haiku's 200k limit. Sonnet 4.6 has 1M context so it fits.
    session, events = await _run_cycle(
        question=question,
        uploads=_load_amenities_uploads(subset=["amenities-main.md", "deep-research-report-2.md"]),
        model=HAIKU,
        synth_override=SONNET,
        run_prompt_master=False,
        checkpoint_name="test1_c7_variance",
    )
    result = _evaluate_test1(session)
    result["fixture_subset"] = ["amenities-main.md", "deep-research-report-2.md"]
    result["model_strategy"] = {
        "intake_analyzer": HAIKU,
        "synthesizer_critic": SONNET,
    }
    result["caveat"] = (
        "Hybrid model strategy adopted after Haiku 4.5 200k context "
        "rejected the synthesizer prompt at 280k+ tokens (4-fixture "
        "version was 407k). Root cause: duplicate facts injection in "
        "synthesizer._build_user_message — analyzer.model_dump() and "
        "_build_facts_section both carry high_relevance_facts. Real "
        "production bug worth filing for follow-up."
    )
    out_path = _save_run("test1_c7_variance", session, events, result)
    print()
    print("=== TEST 1 RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {out_path}")
    return result


async def test2():
    print("=" * 60)
    print("TEST 2 — C3 LOW_EVIDENCE_QUALITY (Haiku 4.5, ~$0.5-1)")
    print("=" * 60)
    question = "Сравни LLM observability платформы Langfuse vs LangSmith vs Helicone для enterprise."
    # Same hybrid strategy as Test 1 for consistency. The synthetic
    # markdown is small enough that Haiku synth would likely fit, but
    # using Sonnet eliminates the variable.
    session, events = await _run_cycle(
        question=question,
        uploads=_llm_obs_uploads(),
        model=HAIKU,
        synth_override=SONNET,
        run_prompt_master=False,
        checkpoint_name="test2_c3_low_evidence",
    )
    result = _evaluate_test2(session)
    out_path = _save_run("test2_c3_low_evidence", session, events, result)
    print()
    print("=== TEST 2 RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {out_path}")
    return result


async def test3():
    print("=" * 60)
    print("TEST 3 — Full v4 cycle integration (Sonnet 4.6, ~$2.5-3.5)")
    print(f"  Hard cap: ${TEST3_HARD_CAP_USD:.2f}")
    print("=" * 60)
    question = "Какие тренды повлияют на девелоперов бизнес-сегмента жилья в Москве на горизонте 3-5 лет?"

    # Pre-flight: confirm the heuristic detects the query
    from smart_report.decomposition_templates import is_russian_re_strategic
    assert is_russian_re_strategic(question), (
        "is_russian_re_strategic returned False for the test query — "
        "decomposition would not fire, test is moot. Aborting."
    )
    print(f"  Heuristic confirms: is_russian_re_strategic = True")

    session, events = await _run_cycle(
        question=question,
        uploads=_load_amenities_uploads(),
        model=SONNET,
        run_prompt_master=True,
        checkpoint_name="test3_c2_decomposition",
    )
    cost_usd = session.total_cost_rub / USD_RUB_RATE
    if cost_usd > TEST3_HARD_CAP_USD:
        print(
            f"\n*** HARD-CAP HIT: ${cost_usd:.4f} > ${TEST3_HARD_CAP_USD:.2f} ***"
        )
        result = {
            "verdict": "FAIL",
            "reason": "hard_cap_exceeded",
            "cost_usd": round(cost_usd, 4),
        }
    else:
        result = _evaluate_test3(session)
    out_path = _save_run("test3_c2_decomposition", session, events, result)
    print()
    print("=== TEST 3 RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {out_path}")
    return result


async def test1_run2_post_fixes():
    """Re-run Test 1 after Fix 1 (synthesizer prompt double-injection) and
    Fix 2 (lint retry threshold 20→100) to confirm cost dropped into the
    expected range. Same hybrid model + same fixtures as Run 1; reuses
    the saved Test 1 checkpoint so we only pay for the Synthesizer pass.

    Acceptance vs Run 1 ($4.85, 3 synth calls):
      - cost_usd <= $1.50
      - synth_invocations == 1 (no Lint or Coverage retry)
      - distinct_grades >= 2 (substance preserved)
      - total_tags >= 6 (substance preserved)

    Hard cap: $2.50.
    """
    print("=" * 60)
    print("TEST 1 RUN 2 — Post-fix verification (Haiku/Sonnet hybrid)")
    print("  Compares against Run 1 baseline ($4.85, 3 synth invocations)")
    print("  Hard cap: $2.50")
    print("=" * 60)
    question = "Какие факторы повлияют на спрос на жильё бизнес-класса в Москве в 2026-2027?"
    session, events = await _run_cycle(
        question=question,
        uploads=_load_amenities_uploads(subset=["amenities-main.md", "deep-research-report-2.md"]),
        model=HAIKU,
        synth_override=SONNET,
        run_prompt_master=False,
        checkpoint_name="test1_c7_variance",  # reuse cached intake+analyze
    )
    cost_usd = session.total_cost_rub / USD_RUB_RATE

    # Count synth calls from emitter trace
    synth_calls = sum(
        1 for e in events
        if e["phase"] == "synthesizer" and "Собираю финальный отчёт" in e["message"]
    )

    # Substance check (re-use Test 1 evaluator)
    base_eval = _evaluate_test1(session)

    if cost_usd > 2.50:
        verdict = "FAIL"
        reason = "hard_cap_exceeded"
    elif cost_usd > 1.50:
        verdict = "DEGRADED"
        reason = "cost_above_target_but_within_cap"
    elif synth_calls != 1:
        verdict = "DEGRADED"
        reason = f"synth_invocations={synth_calls} (expected 1)"
    elif base_eval["distinct_grades"] < 2:
        verdict = "FAIL"
        reason = "variance_lost_post_fix"
    elif base_eval["total_tags"] < 6:
        verdict = "FAIL"
        reason = "tags_lost_post_fix"
    else:
        verdict = "PASS"
        reason = "all_criteria_met"

    result = {
        "verdict": verdict,
        "reason": reason,
        "cost_usd_run2": round(cost_usd, 4),
        "cost_usd_run1_baseline": 4.85,
        "cost_delta_usd": round(4.85 - cost_usd, 4),
        "cost_reduction_pct": round((4.85 - cost_usd) * 100 / 4.85, 1),
        "synth_invocations": synth_calls,
        "synth_invocations_run1_baseline": 3,
        "evidence_grade_distribution": base_eval["evidence_grade_distribution"],
        "distinct_grades": base_eval["distinct_grades"],
        "total_tags": base_eval["total_tags"],
        "model_strategy": {"intake_analyzer": HAIKU, "synthesizer_critic": SONNET},
        "fixture_subset": ["amenities-main.md", "deep-research-report-2.md"],
        "fixes_applied": ["94b7da7 (Finding 1)", "da7f24f (Finding 2)"],
    }

    out_path = _save_run("test1_run2_post_fixes", session, events, result)
    print()
    print("=== TEST 1 RUN 2 RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {out_path}")
    return result


async def test2_haiku_pure():
    """Re-run Test 2 on pure Haiku 4.5 (every stage) after Fix 1 to validate
    cheap-tier viability. Run 1 had to use hybrid Sonnet-synthesis because
    the prompt overflowed Haiku's 200k context. With Fix 1 the prompt
    drops below 110k tokens, so Haiku should fit on every stage.

    Acceptance:
      - cost_usd <= $0.30 (target — Haiku-everywhere is the whole point)
      - All Run 1 substance criteria still pass (LOW_EVIDENCE_QUALITY,
        Cyrillic warning, no sentinel leak, no authoritative sources)
    """
    print("=" * 60)
    print("TEST 2 (Haiku pure) — Cheap-tier viability post-Fix 1")
    print("=" * 60)
    question = "Сравни LLM observability платформы Langfuse vs LangSmith vs Helicone для enterprise."
    # NOTE: do NOT reuse the test2 checkpoint — its analyzer was run on
    # Haiku already, but the checkpoint key includes "anthropic_claude-haiku-4.5"
    # which matches our intended _all_stages(HAIKU) here. So checkpoint
    # IS reusable (same intake+analyze setup).
    session, events = await _run_cycle(
        question=question,
        uploads=_llm_obs_uploads(),
        model=HAIKU,
        synth_override=None,  # KEY DIFFERENCE: pure Haiku on every stage
        run_prompt_master=False,
        checkpoint_name="test2_c3_low_evidence",
    )
    cost_usd = session.total_cost_rub / USD_RUB_RATE
    base_eval = _evaluate_test2(session)
    base_eval["model_strategy"] = "pure_haiku_4.5_every_stage"
    base_eval["cost_usd_target"] = 0.30
    base_eval["cost_run1_hybrid_baseline"] = 0.64
    base_eval["fixes_applied"] = ["94b7da7 (Finding 1)", "da7f24f (Finding 2)"]
    if cost_usd > 0.30 and base_eval["verdict"] == "PASS":
        base_eval["verdict"] = "DEGRADED"
        base_eval["degraded_reason"] = "cost_above_haiku_target_but_substance_ok"
    out_path = _save_run("test2_haiku_pure_post_fixes", session, events, base_eval)
    print()
    print("=== TEST 2 (Haiku pure) RESULT ===")
    print(json.dumps(base_eval, ensure_ascii=False, indent=2))
    print(f"Saved: {out_path}")
    return base_eval


async def step22_planner_acceptance():
    """Live acceptance for v4.5 Phase 2 Step 2.2 — LLM planner end-to-end.

    Uses the Run 1 Test 2 query (LLM observability comparison) which is
    strategic (>=7 words, has "compare" marker) but does NOT match the
    Russian RE domain template. Routing must therefore go through the
    planner LLM path.

    Configuration: pure Haiku 4.5 on every stage including the planner.
    Same uploaded markdown as Run 1 Test 2 (Langfuse/LangSmith/Helicone
    synthetic DR report).

    Acceptance:
      - decomposition_method == "llm_planner" in research_prompt metadata
      - 3-5 sub-questions in research_prompt.sub_questions
      - At least one sub-question has non-empty depends_on
      - Evidence-grade variance >= 2 distinct values (substance unchanged)
      - Total cost <= $0.50 (planner overhead <= $0.10 of that)
      - Hard cap: $1.50
    """
    print("=" * 60)
    print("STEP 2.2 LIVE ACCEPTANCE — Planner path on pure Haiku 4.5")
    print("  Hard cap: $1.50")
    print("=" * 60)
    question = "Compare LLM observability platforms (Langfuse, LangSmith, Helicone) for enterprise scale"

    # Pre-flight: confirm router will pick the planner, not template, not none
    from smart_report.decomposition_templates import (
        is_russian_re_strategic,
        is_strategic_query,
    )
    assert not is_russian_re_strategic(question), (
        "test invariant broken — query should NOT be RU RE strategic"
    )
    assert is_strategic_query(question), (
        "test invariant broken — query should be broad strategic, "
        "otherwise planner won't fire"
    )
    print(f"  Routing: planner path will fire (RU RE template skipped)")

    # NOTE: pure-Haiku run; same as Run 2's test2_haiku pattern but
    # WITH prompt_master enabled this time so the planner actually runs.
    session, events = await _run_cycle(
        question=question,
        uploads=_llm_obs_uploads(),
        model=HAIKU,
        synth_override=None,  # pure Haiku, every stage
        run_prompt_master=True,
        checkpoint_name=None,  # don't reuse — different question topic
    )
    cost_usd = session.total_cost_rub / USD_RUB_RATE

    pm = session.research_prompt
    final = session.final_report

    # Planner-side acceptance
    decomposition_method = (
        getattr(pm, "decomposition_method", "") if pm else ""
    )
    sub_questions = list(getattr(pm, "sub_questions", []) or []) if pm else []
    n_sub = len(sub_questions)
    has_dependency = any(sq.depends_on for sq in sub_questions)

    # Substance side (Phase 1 still works)
    distribution = evidence_grade_distribution(final)
    distinct_grades = sum(1 for v in distribution.values() if v > 0)

    if cost_usd > 1.50:
        verdict = "FAIL"
        reason = "hard_cap_exceeded"
    elif decomposition_method != "llm_planner":
        verdict = "FAIL"
        reason = f"decomposition_method={decomposition_method!r} (expected 'llm_planner')"
    elif not (3 <= n_sub <= 5):
        verdict = "DEGRADED"
        reason = f"sub_questions_count={n_sub} (expected 3-5)"
    elif not has_dependency:
        verdict = "DEGRADED"
        reason = "no sub-question has non-empty depends_on (planner produced flat list)"
    elif distinct_grades < 2:
        verdict = "DEGRADED"
        reason = "evidence-grade variance lost"
    elif cost_usd > 0.50:
        verdict = "DEGRADED"
        reason = "cost_above_target_but_within_cap"
    else:
        verdict = "PASS"
        reason = "all_criteria_met"

    result = {
        "verdict": verdict,
        "reason": reason,
        "cost_usd": round(cost_usd, 4),
        "cost_rub": round(session.total_cost_rub, 2),
        "cost_target": 0.50,
        "cost_hard_cap": 1.50,
        "decomposition_method": decomposition_method,
        "sub_questions_count": n_sub,
        "sub_questions": [
            {
                "id": sq.id,
                "text": sq.text,
                "depends_on": sq.depends_on,
                "rationale": sq.rationale,
                "suggested_sources": sq.suggested_sources,
            }
            for sq in sub_questions
        ],
        "has_dependency_tracked": has_dependency,
        "evidence_grade_distribution": distribution,
        "distinct_grades": distinct_grades,
        "model_strategy": "pure_haiku_4.5_every_stage_including_planner",
        "fixes_applied": [
            "94b7da7 (Finding 1)",
            "da7f24f (Finding 2)",
            "a4cf42c (is_strategic_query)",
            "0e2b7fd (LLM planner)",
            "9296144 (prompt_master 3-way routing)",
        ],
    }

    out_path = _save_run("step22_planner_acceptance", session, events, result)
    print()
    print("=== STEP 2.2 LIVE ACCEPTANCE RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(f"Saved: {out_path}")
    return result


async def step23_24_gaps_acceptance():
    """Live acceptance for v4.5 Phase 2 Steps 2.3 + 2.4 — gap detection
    end-to-end on pure Haiku 4.5.

    Runs the full v4 cycle on the strategic non-RE query (re-uses
    Step 2.2 fixture so the planner fires and sub_questions get
    populated). After synthesize, gaps are already in
    final.metadata via the Step 2.3 orchestrator integration. Then
    invokes the check-gaps endpoint logic directly (in-process, no
    FastAPI server) to also exercise Step 2.4 follow-up prompter.

    Acceptance:
      - sub_questions populated by Step 2.2 planner (≥3)
      - At least one EvidenceGap detected (the LLM observability
        synthetic markdown is intentionally without RU RE auth sources,
        so most sub_questions should fall short of the threshold)
      - For every actionable gap (critical/moderate), a FollowUpPrompt
        is generated with non-empty prompt_text
      - iteration_number == 1, can_iterate_more == True
      - Cost ≤ $1.50 (hard cap), target ≤ $1.00

    Fixture: tests/fixtures/live_runs/2026-04-25_step23_24_gaps_acceptance.json
    """
    print("=" * 60)
    print("STEPS 2.3 + 2.4 LIVE ACCEPTANCE — Gap detection + Follow-up prompts")
    print("  Hard cap: $1.50")
    print("=" * 60)

    question = "Compare LLM observability platforms (Langfuse, LangSmith, Helicone) for enterprise scale"

    # Full v4 cycle on pure Haiku (PM + intake + analyzer + synthesizer)
    session, events = await _run_cycle(
        question=question,
        uploads=_llm_obs_uploads(),
        model=HAIKU,
        synth_override=None,  # pure Haiku every stage
        run_prompt_master=True,
        checkpoint_name=None,
    )

    # Read what Step 2.3 already attached during synthesize
    final = session.final_report
    metadata_gaps = final.metadata.get("evidence_gaps", []) if final else []
    metadata_counts = final.metadata.get("gap_count_by_severity", {}) if final else {}

    # Now exercise the /check-gaps endpoint logic directly (in-process).
    # This re-runs gap_detector (idempotent) + invokes follow_up_prompter
    # for actionable gaps. Cost: gap_detector $0 + follow_up Haiku call ~$0.02.
    from smart_report.api.v4_endpoints import (
        GAP_CHECK_ITERATION_CAP,
        check_gaps,
        _store as _api_store,
    )
    # Inject the session into the API store so check_gaps can find it
    _api_store._sessions[session.session_id] = session
    cost_before_check = session.total_cost_rub
    check_response = await check_gaps(session.session_id)
    cost_check_gaps_rub = session.total_cost_rub - cost_before_check

    cost_usd_total = session.total_cost_rub / USD_RUB_RATE

    # Acceptance evaluation
    n_sub = len(session.research_prompt.sub_questions) if session.research_prompt else 0
    n_gaps = len(check_response.gaps)
    actionable = sum(1 for g in check_response.gaps if g.severity in ("critical", "moderate"))
    n_follow_ups = len(check_response.follow_up_prompts)

    if cost_usd_total > 1.50:
        verdict = "FAIL"
        reason = "hard_cap_exceeded"
    elif n_sub < 3:
        verdict = "FAIL"
        reason = f"sub_questions_count={n_sub} (planner did not fire correctly, expected ≥3)"
    elif n_gaps == 0:
        verdict = "DEGRADED"
        reason = (
            "no gaps detected on a synthetic non-RE markdown — either the "
            "matcher is over-permissive or the test fixture happened to "
            "match every sub_question; manual review needed"
        )
    elif actionable > 0 and n_follow_ups == 0:
        verdict = "FAIL"
        reason = "actionable gaps present but follow_up_prompter returned nothing"
    elif check_response.iteration_number != 1:
        verdict = "FAIL"
        reason = f"iteration_number={check_response.iteration_number} (expected 1 on first call)"
    elif not check_response.can_iterate_more:
        verdict = "FAIL"
        reason = "can_iterate_more=False on first iteration (cap logic broken)"
    elif cost_usd_total > 1.00:
        verdict = "DEGRADED"
        reason = "cost_above_target_but_within_cap"
    else:
        verdict = "PASS"
        reason = "all_criteria_met"

    result = {
        "verdict": verdict,
        "reason": reason,
        "cost_usd_total": round(cost_usd_total, 4),
        "cost_rub_total": round(session.total_cost_rub, 2),
        "cost_check_gaps_rub": round(cost_check_gaps_rub, 4),
        "cost_target_total": 1.00,
        "cost_hard_cap_total": 1.50,
        "model_strategy": "pure_haiku_4.5_every_stage",
        "sub_questions_count": n_sub,
        "sub_questions_summary": [
            {
                "id": sq.id,
                "text": sq.text,
                "evidence_status": sq.evidence_status,
                "authoritative_source_count": sq.authoritative_source_count,
                "matched_sources_count": len(sq.bibliography_refs),
            }
            for sq in (session.research_prompt.sub_questions if session.research_prompt else [])
        ],
        "metadata_evidence_gaps_count": len(metadata_gaps),
        "metadata_gap_count_by_severity": metadata_counts,
        "check_gaps_response": {
            "iteration_number": check_response.iteration_number,
            "can_iterate_more": check_response.can_iterate_more,
            "gap_count_by_severity": check_response.gap_count_by_severity,
            "gaps": [g.model_dump() for g in check_response.gaps],
            "follow_up_prompts": [p.model_dump() for p in check_response.follow_up_prompts],
            "summary_for_analyst": check_response.summary_for_analyst,
        },
        "iteration_cap": GAP_CHECK_ITERATION_CAP,
        "fixes_applied": [
            "Phase 1+2 + Two-fix sprint",
            "5ae0321 (SubQuestion evidence_status)",
            "e4774fb (gap_detector)",
            "5c13357 (orchestrator gap integration)",
            "ba5e033 (follow_up_prompter)",
            "35fab40 (/check-gaps endpoint)",
        ],
    }

    out_path = _save_run("step23_24_gaps_acceptance", session, events, result)
    print()
    print("=== STEPS 2.3 + 2.4 LIVE ACCEPTANCE RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(f"Saved: {out_path}")
    return result


# ---------------------------------------------------------------------------
# Qualitative Comparison Run 1 (apr 2026) — Smart Report vs competitors
# ---------------------------------------------------------------------------
# Three queries, each fed pre-collected DR markdown from the analyst's
# competitor runs (Perplexity DR / ChatGPT DR / Claude Research). Smart
# Report consumes those markdowns through the standard v4 cycle on
# Sonnet 4.6 (deep tier) plus optional /check-gaps for strategic queries
# routed through the LLM planner. Output stored alongside the
# competitor artifacts so the analyst can compare 4 systems × 3 queries.

COMPARISON_OUT_DIR = REPO_ROOT / "tests/fixtures/comparison_runs" / TODAY
COMPARISON_OUT_DIR.mkdir(parents=True, exist_ok=True)

DOWNLOADS = Path("C:/Users/rodina-adm/Downloads")

COMPARISON_QUERIES = [
    {
        "id": "q1_ev",
        "question": (
            "Сравните перспективы трёх лидеров электромобильного рынка в "
            "России (Москвич, АВТОВАЗ, Evolute) на горизонте 3 лет в условиях "
            "конкуренции с китайскими брендами BYD, Geely, Chery"
        ),
        "expected_route": "llm_planner",
        "run_check_gaps": True,
        "uploads": [
            (
                "Перспективы-российских-производителей-электромобилей-в-условиях-китайской-конкуренции-прогноз-на-2026–2029-годы.md",
                "openai_dr",
            ),
            (
                "«Сравните перспективы трёх лидеров электромобильно.md",
                "perplexity",
            ),
        ],
    },
    {
        "id": "q2_moscow_re",
        "question": (
            "Какие тренды повлияют на девелоперов бизнес-сегмента жилья в "
            "Москве в 2026-2027?"
        ),
        "expected_route": "domain_template_ru_re",
        "run_check_gaps": False,  # template path → sub_questions empty
        "uploads": [
            (
                "Тренды,-влияющие-на-московских-девелоперов-жилого-сегмента-в-2026-2027-годах.md",
                "openai_dr",
            ),
            (
                "«Какие тренды повлияют на девелоперов бизнес-сегме.md",
                "perplexity",
            ),
        ],
    },
    {
        "id": "q3_eu_dac",
        "question": (
            "How is Direct Air Capture regulated in the EU and what subsidies "
            "are available in 2026?"
        ),
        "expected_route": "llm_planner",
        "run_check_gaps": True,
        "uploads": [
            (
                "EU-Direct-Air-Capture-Regulation-and-2026-Subsidies-Comprehensive-Framework-and-Funding-Landscape.md",
                "openai_dr",
            ),
        ],
    },
]


def _load_markdown_uploads(specs: list[tuple[str, str]]) -> list[UploadedMarkdown]:
    uploads: list[UploadedMarkdown] = []
    for filename, tool in specs:
        p = DOWNLOADS / filename
        text = p.read_text(encoding="utf-8")
        uploads.append(
            UploadedMarkdown(
                filename=filename,
                content=text,
                detected_tool=tool,
                word_count=len(text.split()),
            )
        )
    return uploads


async def comparison_run_1():
    """Drive Smart Report through 3 queries with the analyst-supplied
    competitor DR markdown as input. Saves one fixture per query plus
    an aggregate summary. Per-query checkpoints preserve partial
    progress: if Q2 crashes, Q1 stays saved on disk so a retry only
    pays for Q2+Q3.
    """
    print("=" * 70)
    print("QUALITATIVE COMPARISON RUN 1 — Smart Report vs competitors")
    print(f"  Output: {COMPARISON_OUT_DIR}")
    print("=" * 70)

    summary: list[dict] = []

    for spec in COMPARISON_QUERIES:
        qid = spec["id"]
        question = spec["question"]
        expected_route = spec["expected_route"]
        run_check_gaps = spec["run_check_gaps"]

        # Skip queries already completed on a prior partial run
        out_path = COMPARISON_OUT_DIR / f"{qid}_smart_report.json"
        if out_path.exists():
            print()
            print(f"--- {qid}: SKIPPING (already saved at {out_path.name})")
            try:
                prev = json.loads(out_path.read_text(encoding="utf-8"))
                summary.append(prev["evaluation"])
            except Exception:
                pass
            continue

        uploads = _load_markdown_uploads(spec["uploads"])
        print()
        print(f"--- {qid}: {question[:80]}{'…' if len(question) > 80 else ''}")
        print(f"  expected route: {expected_route} | check_gaps: {run_check_gaps}")
        print(f"  uploads: {len(uploads)} files, {sum(u.word_count for u in uploads):,} words total")

        session, events = await _run_cycle(
            question=question,
            uploads=uploads,
            model=SONNET,            # Sonnet 4.6 deep tier on every stage
            synth_override=None,
            run_prompt_master=True,
            checkpoint_name=f"comparison_{qid}",
        )
        cost_usd_synth = session.total_cost_rub / USD_RUB_RATE

        # Optional /check-gaps for strategic queries that went through planner
        check_gaps_payload = None
        if run_check_gaps and session.research_prompt and session.research_prompt.sub_questions:
            from smart_report.api.v4_endpoints import check_gaps, _store as _api_store
            _api_store._sessions[session.session_id] = session
            cg = await check_gaps(session.session_id)
            check_gaps_payload = {
                "iteration_number": cg.iteration_number,
                "can_iterate_more": cg.can_iterate_more,
                "gap_count_by_severity": cg.gap_count_by_severity,
                "gaps": [g.model_dump() for g in cg.gaps],
                "follow_up_prompts": [p.model_dump() for p in cg.follow_up_prompts],
                "summary_for_analyst": cg.summary_for_analyst,
            }

        cost_usd_total = session.total_cost_rub / USD_RUB_RATE
        final = session.final_report
        pm = session.research_prompt

        per_query = {
            "query_id": qid,
            "question": question,
            "uploads": [{"filename": fn, "tool": tool} for fn, tool in spec["uploads"]],
            "cost_usd_total": round(cost_usd_total, 4),
            "cost_rub_total": round(session.total_cost_rub, 2),
            "decomposition_method": (
                getattr(pm, "decomposition_method", "") if pm else ""
            ),
            "expected_route": expected_route,
            "route_matches_expectation": (
                getattr(pm, "decomposition_method", "") == expected_route if pm else False
            ),
            "sub_questions_count": len(getattr(pm, "sub_questions", []) or []) if pm else 0,
            "evidence_quality": final.metadata.get("evidence_quality") if final else None,
            "gap_count_by_severity": final.metadata.get("gap_count_by_severity") if final else None,
            "source_count_in_final": len(final.all_sources) if final else 0,
            "main_synthesis_chars": len(final.main_synthesis) if final else 0,
            "evidence_grade_distribution": (
                evidence_grade_distribution(final) if final else None
            ),
            "check_gaps": check_gaps_payload,
        }
        summary.append(per_query)

        # Save full session JSON (includes final_report, analysis, events)
        out_path = COMPARISON_OUT_DIR / f"{qid}_smart_report.json"
        payload = {
            "query_id": qid,
            "question": question,
            "ran_at_utc": datetime.now(timezone.utc).isoformat(),
            "uploads_meta": [{"filename": fn, "tool": tool} for fn, tool in spec["uploads"]],
            "research_prompt": pm.model_dump() if pm else None,
            "analysis": session.analysis.model_dump() if session.analysis else None,
            "final_report": final.model_dump() if final else None,
            "total_cost_rub": session.total_cost_rub,
            "total_cost_usd_at_75_4": round(cost_usd_total, 4),
            "events": events,
            "check_gaps": check_gaps_payload,
            "evaluation": per_query,
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  saved: {out_path}")
        print(f"  cost: ${cost_usd_total:.4f} | route: {per_query['decomposition_method']!r}")

    # Aggregate summary
    aggregate_path = COMPARISON_OUT_DIR / "_aggregate_summary.json"
    aggregate = {
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_cost_usd": round(sum(q["cost_usd_total"] for q in summary), 4),
        "queries": summary,
    }
    aggregate_path.write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print()
    print("=" * 70)
    print("AGGREGATE SUMMARY")
    print("=" * 70)
    print(json.dumps(aggregate, ensure_ascii=False, indent=2, default=str))
    print()
    print(f"Aggregate saved: {aggregate_path}")
    return aggregate


async def step31_q3_rerun():
    """Phase 3 Step 3.1 Task 1.3 — live verification of regulatory-marker
    + EU-registry hot-fixes against the Run 1 Q3 EU DAC fixture.

    Pure Haiku 4.5 every stage. Uses the same EU DAC markdown the
    analyst supplied for Run 1. Acceptance:
      - decomposition_method == "llm_planner" (not "none" — the bug)
      - sub_questions ≥ 3
      - evidence_quality != "LOW_EVIDENCE_QUALITY" (or smaller severity)
      - Cost ≤ $0.50
    """
    print("=" * 60)
    print("STEP 3.1 LIVE VERIFICATION — Q3 EU DAC re-run on Haiku 4.5")
    print("  Hard cap: $0.50")
    print("=" * 60)
    question = (
        "How is Direct Air Capture regulated in the EU and what subsidies "
        "are available in 2026?"
    )

    # Pre-flight: confirm the new markers fire
    from smart_report.decomposition_templates import is_strategic_query
    assert is_strategic_query(question), (
        "Step 3.1 Task 1.1 regression — query should now classify as strategic"
    )
    print(f"  Pre-flight: is_strategic_query=True ✓")

    uploads = _load_markdown_uploads([
        (
            "EU-Direct-Air-Capture-Regulation-and-2026-Subsidies-Comprehensive-Framework-and-Funding-Landscape.md",
            "openai_dr",
        ),
    ])

    session, events = await _run_cycle(
        question=question,
        uploads=uploads,
        model=HAIKU,
        synth_override=None,
        run_prompt_master=True,
        checkpoint_name=None,
    )
    cost_usd = session.total_cost_rub / USD_RUB_RATE
    pm = session.research_prompt
    final = session.final_report

    decomposition_method = getattr(pm, "decomposition_method", "") if pm else ""
    n_sub = len(getattr(pm, "sub_questions", []) or []) if pm else 0
    evidence_quality = final.metadata.get("evidence_quality") if final else None

    if cost_usd > 0.50:
        verdict = "FAIL"
        reason = "hard_cap_exceeded"
    elif decomposition_method != "llm_planner":
        verdict = "FAIL"
        reason = f"decomposition_method={decomposition_method!r} (expected 'llm_planner')"
    elif n_sub < 3:
        verdict = "FAIL"
        reason = f"sub_questions_count={n_sub} (expected ≥3)"
    elif evidence_quality == "LOW_EVIDENCE_QUALITY":
        verdict = "DEGRADED"
        reason = "evidence_quality still LOW — uploaded EU DAC source pool needs richer registry coverage"
    else:
        verdict = "PASS"
        reason = "all_criteria_met"

    result = {
        "verdict": verdict,
        "reason": reason,
        "cost_usd": round(cost_usd, 4),
        "cost_rub": round(session.total_cost_rub, 2),
        "decomposition_method": decomposition_method,
        "sub_questions_count": n_sub,
        "evidence_quality": evidence_quality,
        "source_count": len(final.all_sources) if final else 0,
        "step_3_1_commits": [
            "dff8e5e (regulatory markers)",
            "88ee08f (EU registry tier)",
            "2b60f11 (httpx retry shim)",
        ],
        "run_1_baseline_comparison": {
            "run1_route": "none (BUG)",
            "run1_sub_questions": 0,
            "run1_cost": 2.25,
            "step_3_1_route": decomposition_method,
            "step_3_1_sub_questions": n_sub,
            "step_3_1_cost": round(cost_usd, 4),
        },
    }

    out_path = _save_run("step31_q3_eu_dac_rerun", session, events, result)
    print()
    print("=== STEP 3.1 LIVE VERIFICATION RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(f"Saved: {out_path}")
    return result


async def main(test_name: str):
    runner = {
        "test1": test1,
        "test2": test2,
        "test3": test3,
        "test1_run2": test1_run2_post_fixes,
        "test2_haiku": test2_haiku_pure,
        "step22": step22_planner_acceptance,
        "step23_24": step23_24_gaps_acceptance,
        "comparison1": comparison_run_1,
        "step31_q3": step31_q3_rerun,
    }.get(test_name)
    if runner is None:
        print(
            f"Unknown test: {test_name}. Available: "
            f"test1, test2, test3, test1_run2, test2_haiku, step22, step23_24, "
            f"comparison1."
        )
        sys.exit(2)
    await runner()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
