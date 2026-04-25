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


async def main(test_name: str):
    runner = {"test1": test1, "test2": test2, "test3": test3}.get(test_name)
    if runner is None:
        print(f"Unknown test: {test_name}. Use test1 / test2 / test3.")
        sys.exit(2)
    await runner()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
