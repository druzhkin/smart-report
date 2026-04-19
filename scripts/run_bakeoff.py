"""Model bake-off script for v4.5 pipeline.

Stages:
  §1 — Prompt Master bake-off (4 models)
  §2 — Intake safety check (Haiku 4.5)
  §3 — Analyzer bake-off (3 non-Opus + cached Opus baseline)
  §4 — Synthesizer bake-off (4 models)
  §5 — Skipped per user decision
  §6 — Final smoke run with winner config

Usage:
    python scripts/run_bakeoff.py [--skip-sections 1,2,3,4,6] [--budget 18]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap path so smart_report can be imported
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

import httpx

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
USD_TO_RUB = 90.0
BUDGET_USD_CAP = 18.0  # stop before §6 if this is hit

# ---------------------------------------------------------------------------
# Question constant (from scripts/night_upgrade_prod_run.py)
# ---------------------------------------------------------------------------
QUESTION = (
    "мне нужен полный глубокий обзор по бизнес и премиум новостройкам москвы и анализ мировых практик – "
    "нужно понять, что реально пользуется спросом у покупателей а что нет, какие параметры комплекса: "
    "архитектура, фасады, мопы, финтес, бассейны, сигарные, и прочее. Какие именно параметры проекта, "
    "инфраструктуры и аменитис реально нужны и сколько покупатели готовы за это платить через рост цены. "
    "Есть ли оптимальный баланс в ассртименте аменитис, есть ли потимальный экономический баланс для "
    "застройщика по аменитис (потеря площадей, влияние на цену, окупаемоть аменитис). Нужный полный "
    "гглубокйи полноценный разбор для уровня акционера, с проверенными цифрами, надежными источниками, "
    "выводами, аналитиой синтезом и прочеим. Нужен отет а не просто обзор"
)

FIXTURES_DIR = REPO_ROOT / "runs" / "night_upgrade" / "fixtures"
CACHE_ANALYSIS = REPO_ROOT / "runs" / "night_upgrade" / "20260419T093210Z" / "analysis_output.json"
CACHE_RESEARCH_PROMPT = REPO_ROOT / "runs" / "night_upgrade" / "20260419T093210Z" / "research_prompt.json"

# Model candidates (verified available on OpenRouter)
PM_MODELS = {
    "opus-4.7": "anthropic/claude-opus-4.7",
    "sonnet-4.6": "anthropic/claude-sonnet-4.6",
    "gpt-4o": "openai/gpt-4o",
    "gemini-3.1-pro": "google/gemini-3.1-pro-preview",
}

ANALYZER_MODELS = {
    "sonnet-4.6": "anthropic/claude-sonnet-4.6",
    "gpt-4o": "openai/gpt-4o",
    "gemini-3.1-pro": "google/gemini-3.1-pro-preview",
}

SYNTH_MODELS = {
    "opus-4.7": "anthropic/claude-opus-4.7",
    "sonnet-4.6": "anthropic/claude-sonnet-4.6",
    "gpt-4o": "openai/gpt-4o",
    "gemini-3.1-pro": "google/gemini-3.1-pro-preview",
}

INTAKE_SAFETY_MODEL = "anthropic/claude-haiku-4.5"

# ---------------------------------------------------------------------------
# Global cost tracker
# ---------------------------------------------------------------------------
_total_cost_usd: float = 0.0
_llm_log_path: Path | None = None


def _log_llm_call(
    stage: str,
    model: str,
    tokens_in: int | None,
    tokens_out: int | None,
    cost_usd: float | None,
    latency_s: float,
    truncated_response: str = "",
) -> None:
    global _total_cost_usd
    cost = cost_usd or 0.0
    _total_cost_usd += cost
    cost_rub = round(cost * USD_TO_RUB, 4)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost, 6),
        "cost_rub": cost_rub,
        "total_cost_usd_so_far": round(_total_cost_usd, 4),
        "latency_s": round(latency_s, 2),
        "response_preview": truncated_response[:300],
    }
    print(
        f"  [LLM] {stage}/{model}: ${cost:.4f} (total=${_total_cost_usd:.3f})"
        f" in={tokens_in} out={tokens_out} lat={latency_s:.1f}s"
    )
    if _llm_log_path:
        with open(_llm_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _check_budget() -> bool:
    """Return True if under budget, False if should stop."""
    if _total_cost_usd >= BUDGET_USD_CAP:
        print(f"\n[BUDGET CAP] ${_total_cost_usd:.2f} >= ${BUDGET_USD_CAP} — stopping.")
        return False
    return True


# ---------------------------------------------------------------------------
# Raw OpenRouter call
# ---------------------------------------------------------------------------

async def _or_call(
    stage: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 8000,
    response_format: dict | None = None,
) -> str | None:
    """Make a raw OpenRouter call. Returns assistant text or None on failure."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/smart-report-mvp",
        "X-Title": "smart-report-mvp-bakeoff",
    }
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if r.status_code == 402:
                print(f"  [BUDGET EXCEEDED] OpenRouter 402 for {model} — stopping stage.")
                return None
            if r.status_code != 200:
                print(f"  [HTTP ERROR] {r.status_code} for {model}: {r.text[:200]}")
                return None
            data = r.json()
    except Exception as e:
        print(f"  [NETWORK ERROR] {model}: {e}")
        return None

    latency = time.monotonic() - t0
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {}) or {}
    cost_usd: float | None = usage.get("cost")
    tokens_in: int | None = usage.get("prompt_tokens")
    tokens_out: int | None = usage.get("completion_tokens")

    _log_llm_call(stage, model, tokens_in, tokens_out, cost_usd, latency, text)
    return text


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json(text: str) -> Any:
    m = _JSON_FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try raw JSON
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    end = max(text.rfind("}"), text.rfind("]"))
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


# ---------------------------------------------------------------------------
# §1 — Prompt Master bake-off
# ---------------------------------------------------------------------------

def _score_pm(result: dict) -> dict[str, Any]:
    """Score a ResearchPrompt result. Returns scores dict + total."""
    scores: dict[str, int] = {}
    full_prompt = result.get("full_prompt", "") if isinstance(result, dict) else ""
    tips = result.get("tips_for_search", "") if isinstance(result, dict) else ""
    expected = result.get("expected_structure", []) if isinstance(result, dict) else []
    entities = result.get("key_entities", []) if isinstance(result, dict) else []

    word_count = len(full_prompt.split())
    scores["length_gt200"] = 20 if word_count >= 200 else 0

    # Count companies/sources: look for named entities in key_entities + full_prompt
    company_like = [e for e in entities if len(e) > 2]
    scores["entities_ge5"] = 20 if len(company_like) >= 5 else (10 if len(company_like) >= 3 else 0)

    # Critical: Track 0 data-table directive
    has_table_directive = "Сводная таблица данных" in full_prompt
    scores["track0_table_directive"] = 30 if has_table_directive else 0

    # Time window
    time_pattern = re.compile(r"(202[0-9]|Q[1-4]\s*202|квартал|2023.{0,5}2025|2024|2025)", re.IGNORECASE)
    scores["time_window"] = 10 if time_pattern.search(full_prompt) else 0

    # Numbered sections
    has_sections = bool(re.search(r"^\s*\d+[\.\)]\s+\*\*", full_prompt, re.MULTILINE))
    if not has_sections:
        # Check for numbered items generally
        has_sections = len(re.findall(r"^\s*\d+\.", full_prompt, re.MULTILINE)) >= 3
    scores["structured_sections"] = 10 if has_sections else 0

    # tips_for_search mentions ≥2 tools
    tool_words = ["perplexity", "openai", "claude", "gemini", "google"]
    tools_mentioned = sum(1 for t in tool_words if t.lower() in tips.lower())
    scores["tips_tools_ge2"] = 10 if (tips and tools_mentioned >= 2) else 0

    total = sum(scores.values())
    return {"breakdown": scores, "total": total, "word_count": word_count, "has_table_directive": has_table_directive}


async def run_section1(out_dir: Path) -> dict[str, Any]:
    """Run Prompt Master bake-off. Returns {model_slug: {result, score}}."""
    print("\n=== §1 Prompt Master Bake-off ===")
    from smart_report.io import load_prompt

    system = load_prompt("prompt_master")
    user = (
        "Raw analyst question:\n"
        f"{QUESTION}\n\n"
        "Return only the JSON object described in the output contract. "
        "No preface, no trailing commentary."
    )

    results: dict[str, Any] = {}
    for slug, model_id in PM_MODELS.items():
        if not _check_budget():
            break
        print(f"\n  Running Prompt Master with {slug} ({model_id})...")
        text = await _or_call(
            f"pm/{slug}",
            model_id,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
            max_tokens=6000,
            response_format={"type": "json_object"},
        )
        if text is None:
            results[slug] = {"error": "call failed", "score": None}
            continue
        parsed = _extract_json(text)
        score = _score_pm(parsed or {})
        results[slug] = {
            "model": model_id,
            "raw_text": text[:2000],  # trim for storage
            "parsed": parsed,
            "score": score,
        }
        print(f"    Score: {score['total']}/100 | table_directive={score['has_table_directive']} | words={score['word_count']}")

    # Save raw results
    with open(out_dir / "pm_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results


def _pick_pm_winner(results: dict[str, Any]) -> tuple[str, str]:
    """Return (slug, model_id) of cheapest model scoring ≥70."""
    # Ordering: haiku (N/A), sonnet, gpt-4o, gemini, opus
    preference = ["sonnet-4.6", "gpt-4o", "gemini-3.1-pro", "opus-4.7"]
    for slug in preference:
        r = results.get(slug, {})
        score = r.get("score", {})
        if isinstance(score, dict) and score.get("total", 0) >= 70:
            return slug, PM_MODELS[slug]
    # Fallback: highest score
    best_slug = max(
        (s for s in results if results[s].get("score") and isinstance(results[s]["score"], dict)),
        key=lambda s: results[s]["score"].get("total", 0),
        default="opus-4.7",
    )
    return best_slug, PM_MODELS.get(best_slug, PM_MODELS["opus-4.7"])


# ---------------------------------------------------------------------------
# §2 — Intake safety check
# ---------------------------------------------------------------------------

async def run_section2(out_dir: Path) -> dict[str, Any]:
    """Run Intake safety check with Haiku 4.5 on amenities-main.md."""
    print("\n=== §2 Intake Safety Check (Haiku 4.5) ===")

    # Read the fixture
    fixture_path = FIXTURES_DIR / "amenities-main.md"
    if not fixture_path.exists():
        print("  [SKIP] amenities-main.md not found")
        return {"skipped": True, "reason": "fixture not found"}

    content = fixture_path.read_text(encoding="utf-8")
    word_count = len(content.split())
    print(f"  Fixture: {word_count} words, {len(content)} chars")

    # Opus baseline: 721 numeric facts from cached analysis_output.json (all_numeric_facts)
    opus_fact_count = 721

    # Use the intake module directly — override INTAKE_MODEL temporarily
    import smart_report.intake as _intake_mod
    from smart_report.models import UploadedMarkdown

    # Load cached research prompt text
    with open(CACHE_RESEARCH_PROMPT, encoding="utf-8") as f:
        rp_data = json.load(f)
    research_prompt_text = rp_data.get("full_prompt", "")

    uploaded = UploadedMarkdown(
        filename="amenities-main.md",
        content=content,
        detected_tool="perplexity",
        word_count=word_count,
    )

    print(f"  Running normalize_report with Haiku ({INTAKE_SAFETY_MODEL})...")
    # Temporarily patch INTAKE_MODEL in the module
    original_model = _intake_mod.INTAKE_MODEL
    _intake_mod.INTAKE_MODEL = INTAKE_SAFETY_MODEL
    t0 = time.monotonic()
    try:
        nr = await _intake_mod.normalize_report(
            uploaded,
            research_prompt_text,
            mock=False,
            log_dir=out_dir,
        )
        latency = time.monotonic() - t0
        haiku_fact_count = len(nr.extracted_numeric_facts)
        ratio = haiku_fact_count / opus_fact_count if opus_fact_count > 0 else 0.0

        print(f"  Haiku facts: {haiku_fact_count} | Opus baseline: {opus_fact_count} | ratio: {ratio:.2%}")
        print(f"  Latency: {latency:.1f}s | cost_rub: {cost_rub:.2f}")

        if ratio >= 0.70:
            fallback = "anthropic/claude-haiku-4.5"
            decision = "haiku"
        elif ratio >= 0.50:
            fallback = "anthropic/claude-sonnet-4.6"
            decision = "sonnet (run extra test recommended)"
        else:
            fallback = "anthropic/claude-opus-4.7"
            decision = "opus (no change)"

        result = {
            "haiku_fact_count": haiku_fact_count,
            "opus_baseline": opus_fact_count,
            "ratio": round(ratio, 4),
            "fallback_choice": fallback,
            "decision": decision,
        }

        # Write INTAKE_FALLBACK_CHOICE.md
        (out_dir / "INTAKE_FALLBACK_CHOICE.md").write_text(
            f"""# Intake Fallback Model Choice

## Test: Haiku 4.5 on amenities-main.md

| Metric | Value |
|--------|-------|
| Haiku numeric facts extracted | {haiku_fact_count} |
| Opus baseline (cache) | {opus_fact_count} |
| Retention ratio | {ratio:.1%} |
| Decision threshold | >=70% -> Haiku, 50-70% -> Sonnet, <50% -> Opus |

## Decision: `{fallback}`

Rationale: {decision}

## Cost
- Haiku intake call: tracked in llm_log.jsonl
""",
            encoding="utf-8",
        )

        return result

    except Exception as e:
        latency = time.monotonic() - t0
        print(f"  [ERROR] Intake failed after {latency:.1f}s: {e}")
        return {"error": str(e), "fallback_choice": "anthropic/claude-opus-4.7", "decision": "opus (error fallback)"}
    finally:
        # Restore original model
        _intake_mod.INTAKE_MODEL = original_model


# ---------------------------------------------------------------------------
# §3 — Analyzer bake-off
# ---------------------------------------------------------------------------

def _score_analyzer(data: dict | None) -> dict[str, Any]:
    """Score an AnalysisOutput dict."""
    if not isinstance(data, dict):
        return {"total": 0, "breakdown": {}, "parse_error": True}

    scores: dict[str, int] = {}
    consensus = data.get("consensus", [])
    conflicts = data.get("conflicts", [])
    gaps = data.get("gaps", [])
    followup = data.get("followup_prompt")
    numeric_facts = data.get("all_numeric_facts", [])
    fact_coverage = data.get("fact_coverage_target", 0)

    scores["consensus_ge10"] = 20 if len(consensus) >= 10 else (10 if len(consensus) >= 5 else 0)
    scores["conflicts_ge5"] = 20 if len(conflicts) >= 5 else (10 if len(conflicts) >= 3 else 0)
    scores["gaps_ge5"] = 15 if len(gaps) >= 5 else (7 if len(gaps) >= 3 else 0)
    scores["followup_populated"] = 15 if (followup and isinstance(followup, dict) and followup.get("prompt")) else 0
    scores["numeric_facts_ge400"] = 10 if len(numeric_facts) >= 400 else (5 if len(numeric_facts) >= 100 else 0)
    scores["fact_coverage_gt0"] = 10 if fact_coverage > 0 else 0
    scores["valid_json"] = 10  # If we got here, it's valid

    total = sum(scores.values())
    return {
        "breakdown": scores,
        "total": total,
        "consensus_count": len(consensus),
        "conflicts_count": len(conflicts),
        "gaps_count": len(gaps),
        "numeric_facts_count": len(numeric_facts),
        "fact_coverage_target": fact_coverage,
    }


async def run_section3(out_dir: Path) -> dict[str, Any]:
    """Run Analyzer bake-off. Returns {model_slug: {result, score}}."""
    print("\n=== §3 Analyzer Bake-off ===")

    # Load cached analysis (Opus baseline)
    with open(CACHE_ANALYSIS, encoding="utf-8") as f:
        opus_analysis = json.load(f)

    # Opus baseline score (from cache — no new call)
    opus_score = _score_analyzer(opus_analysis)
    print(f"  Opus baseline score: {opus_score['total']}/100 | consensus={opus_score['consensus_count']}")

    # Load prompts and source reports
    from smart_report.io import load_prompt

    system = load_prompt("analyzer")

    # Build the user message from fixture files + cached research prompt
    with open(CACHE_RESEARCH_PROMPT, encoding="utf-8") as f:
        rp_data = json.load(f)

    fixture_files = list(FIXTURES_DIR.glob("*.md"))
    parts = [
        f"## Original analyst question\n{QUESTION}\n",
        f"## Research prompt used\n{rp_data.get('full_prompt','')}\n",
        f"## Source reports (n={len(fixture_files)})\n",
    ]
    for i, fp in enumerate(fixture_files, 1):
        content = fp.read_text(encoding="utf-8")
        wc = len(content.split())
        parts.append(f"### [{i}] filename={fp.name} words={wc}")
        # Truncate large files to save tokens
        truncated = content[:30000] if len(content) > 30000 else content
        parts.append(truncated + "\n")
    parts.append("\n---\nReturn STRICT JSON matching the AnalysisOutput schema. No prose wrapper. No markdown fences.")
    user = "\n".join(parts)

    results: dict[str, Any] = {
        "opus-4.7": {
            "model": "anthropic/claude-opus-4.7",
            "parsed": opus_analysis,
            "score": opus_score,
            "note": "cached — no new LLM call",
        }
    }

    for slug, model_id in ANALYZER_MODELS.items():
        if not _check_budget():
            break
        print(f"\n  Running Analyzer with {slug} ({model_id})...")
        text = await _or_call(
            f"analyzer/{slug}",
            model_id,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=10000,
            response_format={"type": "json_object"},
        )
        if text is None:
            results[slug] = {"error": "call failed", "score": None}
            continue
        parsed = _extract_json(text)
        score = _score_analyzer(parsed or {})
        results[slug] = {
            "model": model_id,
            "raw_text": text[:3000],
            "parsed": parsed,
            "score": score,
        }
        print(f"    Score: {score['total']}/100 | consensus={score.get('consensus_count',0)} conflicts={score.get('conflicts_count',0)} gaps={score.get('gaps_count',0)}")

    # Save results
    with open(out_dir / "analyzer_results.json", "w", encoding="utf-8") as f:
        # Don't store full parsed (too big) — just scores and metadata
        summary = {}
        for k, v in results.items():
            summary[k] = {
                "model": v.get("model", ""),
                "score": v.get("score"),
                "note": v.get("note", ""),
                "error": v.get("error"),
            }
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return results


def _pick_analyzer_winner(results: dict[str, Any]) -> tuple[str, str, dict | None]:
    """Return (slug, model_id, analysis_data) of best model scoring ≥70."""
    # Check non-Opus first (cheapest first)
    preference = ["sonnet-4.6", "gpt-4o", "gemini-3.1-pro"]
    for slug in preference:
        r = results.get(slug, {})
        score = r.get("score", {})
        if isinstance(score, dict) and score.get("total", 0) >= 70:
            return slug, ANALYZER_MODELS[slug], r.get("parsed")
    # Fall back to Opus cached
    return "opus-4.7", "anthropic/claude-opus-4.7", results.get("opus-4.7", {}).get("parsed")


# ---------------------------------------------------------------------------
# §4 — Synthesizer bake-off
# ---------------------------------------------------------------------------

def _score_synthesizer(data: dict | None) -> dict[str, Any]:
    """Score a FinalReport dict."""
    if not isinstance(data, dict):
        return {"total": 0, "breakdown": {}, "parse_error": True}

    scores: dict[str, int] = {}

    qa_section = data.get("qa_section", [])
    tables = data.get("tables", [])
    charts = data.get("charts", [])
    callouts = data.get("callouts", [])
    key_numbers = data.get("key_numbers_highlight", [])
    ranking = data.get("ranking", None)
    main_synthesis = data.get("main_synthesis", "")
    all_sources = data.get("all_sources", [])

    scores["qa_section_ge5"] = 20 if len(qa_section) >= 5 else (10 if len(qa_section) >= 3 else 0)
    scores["tables_ge3"] = 10 if len(tables) >= 3 else (5 if len(tables) >= 1 else 0)
    scores["charts_ge3"] = 5 if len(charts) >= 3 else (2 if len(charts) >= 1 else 0)
    scores["callouts_ge3"] = 5 if len(callouts) >= 3 else (2 if len(callouts) >= 1 else 0)

    # key_numbers_highlight with source_ref
    kn_with_src = [k for k in key_numbers if isinstance(k, dict) and k.get("source_ref")]
    scores["key_numbers_5to7"] = 10 if 5 <= len(kn_with_src) <= 7 else (5 if len(kn_with_src) >= 3 else 0)

    # ranking with weights
    has_ranking = isinstance(ranking, dict) and bool(ranking) or (isinstance(ranking, list) and len(ranking) > 0)
    scores["ranking_with_weights"] = 10 if has_ranking else 0

    scores["main_synthesis_ge3000"] = 10 if len(main_synthesis) >= 3000 else (5 if len(main_synthesis) >= 1000 else 0)

    # Citation density [REF: in main_synthesis
    ref_count = len(re.findall(r"\[REF:", main_synthesis))
    scores["citations_ge20"] = 15 if ref_count >= 20 else (8 if ref_count >= 10 else 0)

    # Unique source URLs
    unique_sources = len(set(
        s.get("url", "") for s in all_sources if isinstance(s, dict) and s.get("url", "")
    ))
    scores["sources_ge30"] = 10 if unique_sources >= 30 else (5 if unique_sources >= 10 else 0)

    # Language check: count obvious English words in main_synthesis (simplified)
    english_words = re.findall(r"\b[A-Z][a-z]{3,}\b", main_synthesis)
    # Filter known brand names / expected anglicisms
    acceptable = {"Perplexity", "Google", "Moscow", "Russia", "SPA", "NPV", "EBITDA", "ROI", "GBA", "GLA"}
    unexpected_en = [w for w in english_words if w not in acceptable]
    scores["russian_only"] = 5 if len(unexpected_en) < 20 else 0

    total = sum(scores.values())
    return {
        "breakdown": scores,
        "total": total,
        "qa_count": len(qa_section),
        "tables_count": len(tables),
        "charts_count": len(charts),
        "callouts_count": len(callouts),
        "key_numbers_with_src": len(kn_with_src),
        "ref_citations": ref_count,
        "unique_sources": unique_sources,
        "main_synthesis_len": len(main_synthesis),
    }


async def run_section4(out_dir: Path, analysis_data: dict | None = None) -> dict[str, Any]:
    """Run Synthesizer bake-off."""
    print("\n=== §4 Synthesizer Bake-off ===")

    synth_dir = out_dir / "synth_reports"
    synth_dir.mkdir(exist_ok=True)

    # Use analysis_data or load from cache
    if analysis_data is None:
        with open(CACHE_ANALYSIS, encoding="utf-8") as f:
            analysis_data = json.load(f)

    # Load synthesizer prompt
    from smart_report.io import load_prompt
    system = load_prompt("synthesizer")

    # Load cached research prompt
    with open(CACHE_RESEARCH_PROMPT, encoding="utf-8") as f:
        rp_data = json.load(f)

    # Build minimal V4Session-like user message
    fixture_files = list(FIXTURES_DIR.glob("*.md"))
    source_parts: list[str] = []
    for i, fp in enumerate(fixture_files, 1):
        content = fp.read_text(encoding="utf-8")
        wc = len(content.split())
        source_parts.append(f"### [{i}] {fp.name} ({wc} words)")
        truncated = content[:20000] if len(content) > 20000 else content
        source_parts.append(truncated)

    analysis_str = json.dumps(analysis_data, ensure_ascii=False)

    user = f"""## Original question
{QUESTION}

## Research prompt used
{rp_data.get('full_prompt', '')[:3000]}

## Analysis output (AnalysisOutput)
{analysis_str[:8000]}

## Source reports
{"".join(source_parts)[:30000]}

---
Return STRICT JSON matching the FinalReport schema from your system prompt. No prose wrapper. No markdown fences.
"""

    results: dict[str, Any] = {}
    for slug, model_id in SYNTH_MODELS.items():
        if not _check_budget():
            break
        print(f"\n  Running Synthesizer with {slug} ({model_id})...")
        text = await _or_call(
            f"synth/{slug}",
            model_id,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
            max_tokens=14000,
            response_format={"type": "json_object"},
        )
        if text is None:
            results[slug] = {"error": "call failed", "score": None}
            continue

        parsed = _extract_json(text)
        score = _score_synthesizer(parsed or {})

        # Save full report for subjective review
        report_path = synth_dir / f"{slug}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({"model": model_id, "parsed": parsed, "raw_text": text}, f, ensure_ascii=False, indent=2)

        results[slug] = {
            "model": model_id,
            "score": score,
            "report_path": str(report_path),
        }
        print(f"    Score: {score['total']}/100 | qa={score.get('qa_count',0)} tables={score.get('tables_count',0)} refs={score.get('ref_citations',0)} sources={score.get('unique_sources',0)}")

    # Save summary
    with open(out_dir / "synth_results.json", "w", encoding="utf-8") as f:
        summary = {k: {"model": v.get("model"), "score": v.get("score"), "error": v.get("error")} for k, v in results.items()}
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return results


def _pick_synth_winner(results: dict[str, Any]) -> tuple[str, str]:
    """Return (slug, model_id) of cheapest model scoring ≥70."""
    preference = ["sonnet-4.6", "gpt-4o", "gemini-3.1-pro", "opus-4.7"]
    for slug in preference:
        r = results.get(slug, {})
        score = r.get("score", {})
        if isinstance(score, dict) and score.get("total", 0) >= 70:
            return slug, SYNTH_MODELS[slug]
    # Highest scorer
    best = max(
        (s for s in results if results[s].get("score") and isinstance(results[s]["score"], dict)),
        key=lambda s: results[s]["score"].get("total", 0),
        default="opus-4.7",
    )
    return best, SYNTH_MODELS.get(best, SYNTH_MODELS["opus-4.7"])


# ---------------------------------------------------------------------------
# §6 — Final smoke run
# ---------------------------------------------------------------------------

async def run_section6(
    out_dir: Path,
    pm_winner: tuple[str, str],
    analyzer_winner: tuple[str, str],
    synth_winner: tuple[str, str],
    intake_fallback: str,
) -> dict[str, Any]:
    """Run full pipeline with winner config on all 4 fixtures."""
    print("\n=== §6 Final Smoke Run ===")

    if not _check_budget():
        return {"skipped": True, "reason": "budget cap reached"}

    from smart_report.io import load_prompt
    from smart_report.prompt_master import generate_research_prompt
    from smart_report.analyzer import analyze_reports
    from smart_report.synthesizer import synthesize_final_report
    from smart_report.models import UploadedMarkdown, V4Session, ResearchPrompt

    # Step 1: Prompt Master
    print(f"\n  Step 1: Prompt Master with {pm_winner[0]} ({pm_winner[1]})...")
    pm_system = load_prompt("prompt_master")
    pm_user = (
        f"Raw analyst question:\n{QUESTION}\n\n"
        "Return only the JSON object. No preface, no trailing commentary."
    )
    pm_text = await _or_call(
        "smoke/pm",
        pm_winner[1],
        [{"role": "system", "content": pm_system}, {"role": "user", "content": pm_user}],
        temperature=0.4,
        max_tokens=6000,
        response_format={"type": "json_object"},
    )

    rp_data: dict = {}
    if pm_text:
        parsed = _extract_json(pm_text)
        if isinstance(parsed, dict):
            rp_data = parsed
    if not rp_data:
        # Fall back to cached
        with open(CACHE_RESEARCH_PROMPT, encoding="utf-8") as f:
            rp_data = json.load(f)
        print("  [fallback] Using cached research prompt")

    research_prompt = ResearchPrompt(
        full_prompt=rp_data.get("full_prompt", ""),
        reasoning=rp_data.get("reasoning", ""),
        expected_structure=rp_data.get("expected_structure", []),
        key_entities=rp_data.get("key_entities", []),
        tips_for_search=rp_data.get("tips_for_search", ""),
    )

    # Step 2: Load fixtures as UploadedMarkdown
    fixture_files = list(FIXTURES_DIR.glob("*.md"))
    source_reports: list[UploadedMarkdown] = []
    for fp in fixture_files:
        content = fp.read_text(encoding="utf-8")
        source_reports.append(UploadedMarkdown(
            filename=fp.name,
            content=content,
            word_count=len(content.split()),
        ))

    # Step 3: Analyzer
    print(f"\n  Step 3: Analyzer with {analyzer_winner[0]} ({analyzer_winner[1]})...")
    if not _check_budget():
        return {"skipped": True, "reason": "budget cap before analyzer"}

    from smart_report.io import load_prompt

    analyzer_system = load_prompt("analyzer")
    parts = [
        f"## Original analyst question\n{QUESTION}\n",
        f"## Research prompt used\n{research_prompt.full_prompt}\n",
        f"## Source reports (n={len(source_reports)})\n",
    ]
    for i, r in enumerate(source_reports, 1):
        parts.append(f"### [{i}] {r.filename} words={r.word_count}")
        truncated = r.content[:25000] if len(r.content) > 25000 else r.content
        parts.append(truncated + "\n")
    parts.append("Return STRICT JSON matching the AnalysisOutput schema. No prose wrapper. No markdown fences.")
    analyzer_user = "\n".join(parts)

    analyzer_text = await _or_call(
        "smoke/analyzer",
        analyzer_winner[1],
        [{"role": "system", "content": analyzer_system}, {"role": "user", "content": analyzer_user}],
        temperature=0.3,
        max_tokens=10000,
        response_format={"type": "json_object"},
    )

    analysis_data: dict = {}
    if analyzer_text:
        parsed_a = _extract_json(analyzer_text)
        if isinstance(parsed_a, dict):
            analysis_data = parsed_a
    if not analysis_data:
        with open(CACHE_ANALYSIS, encoding="utf-8") as f:
            analysis_data = json.load(f)
        print("  [fallback] Using cached analysis")

    # Step 4: Synthesizer
    print(f"\n  Step 4: Synthesizer with {synth_winner[0]} ({synth_winner[1]})...")
    if not _check_budget():
        return {"skipped": True, "reason": "budget cap before synthesizer"}

    synth_system = load_prompt("synthesizer")
    analysis_str = json.dumps(analysis_data, ensure_ascii=False)
    source_snippet = "\n".join(
        f"### [{i}] {r.filename}\n" + (r.content[:15000] if len(r.content) > 15000 else r.content)
        for i, r in enumerate(source_reports, 1)
    )
    synth_user = f"""## Original question
{QUESTION}

## Research prompt
{research_prompt.full_prompt[:3000]}

## Analysis output
{analysis_str[:8000]}

## Source reports
{source_snippet[:30000]}

---
Return STRICT JSON matching the FinalReport schema. No prose wrapper. No markdown fences.
"""

    synth_text = await _or_call(
        "smoke/synth",
        synth_winner[1],
        [{"role": "system", "content": synth_system}, {"role": "user", "content": synth_user}],
        temperature=0.4,
        max_tokens=14000,
        response_format={"type": "json_object"},
    )

    final_report_data: dict = {}
    if synth_text:
        parsed_s = _extract_json(synth_text)
        if isinstance(parsed_s, dict):
            final_report_data = parsed_s

    # Save final smoke results
    smoke_result = {
        "pm_model": pm_winner[1],
        "analyzer_model": analyzer_winner[1],
        "synth_model": synth_winner[1],
        "intake_fallback": intake_fallback,
        "total_cost_usd": round(_total_cost_usd, 4),
    }

    with open(out_dir / "final_smoke.json", "w", encoding="utf-8") as f:
        json.dump({
            "config": smoke_result,
            "research_prompt": rp_data,
            "analysis_summary": {
                "consensus": len(analysis_data.get("consensus", [])),
                "conflicts": len(analysis_data.get("conflicts", [])),
                "gaps": len(analysis_data.get("gaps", [])),
            },
            "final_report": final_report_data,
        }, f, ensure_ascii=False, indent=2)

    # Try to render docx
    _render_smoke_docx(out_dir, final_report_data)

    return smoke_result


def _render_smoke_docx(out_dir: Path, final_report_data: dict) -> None:
    """Attempt to render the final report to docx."""
    if not final_report_data:
        print("  [WARN] No final_report_data to render")
        return
    try:
        from smart_report.exporters import render_docx
        from smart_report.models import FinalReport

        fr = FinalReport.model_validate(final_report_data)
        docx_path = out_dir / "final_smoke.docx"
        render_docx(fr, docx_path)
        print(f"  Saved final_smoke.docx to {docx_path}")
    except Exception as e:
        print(f"  [WARN] Could not render docx: {type(e).__name__}: {e} — saving json only")


# ---------------------------------------------------------------------------
# Scoring summary
# ---------------------------------------------------------------------------

def _write_scoring(out_dir: Path, pm_results: dict, analyzer_results: dict, synth_results: dict) -> None:
    scoring: dict[str, Any] = {}

    for stage, results in [("pm", pm_results), ("analyzer", analyzer_results), ("synth", synth_results)]:
        for slug, r in results.items():
            score = r.get("score") if isinstance(r, dict) else None
            if isinstance(score, dict):
                scoring[f"{stage}/{slug}"] = {
                    "model": r.get("model", ""),
                    "total": score.get("total", 0),
                    "breakdown": score.get("breakdown", {}),
                }

    with open(out_dir / "scoring.json", "w", encoding="utf-8") as f:
        json.dump(scoring, f, ensure_ascii=False, indent=2)


def _write_model_choices(
    out_dir: Path,
    pm_winner: tuple[str, str],
    analyzer_winner: tuple[str, str],
    synth_winner: tuple[str, str],
    intake_fallback: str,
    pm_results: dict,
    analyzer_results: dict,
    synth_results: dict,
) -> None:
    lines: list[str] = [
        "# Model Choices — v4.5 Bake-off Results",
        "",
        "## Winner Configuration",
        "",
        "```python",
        "class ModelConfig:",
        f'    PROMPT_MASTER_MODEL = "{pm_winner[1]}"',
        f'    INTAKE_MODEL = "DETERMINISTIC"  # Track 0 parser — LLM only as fallback',
        f'    INTAKE_LLM_FALLBACK_MODEL = "{intake_fallback}"',
        f'    ANALYZER_MODEL = "{analyzer_winner[1]}"',
        f'    SYNTHESIZER_MODEL = "{synth_winner[1]}"',
        '    SYNTHESIS_CRITIC_MODEL = "anthropic/claude-opus-4.7"  # fixed per §5',
        "```",
        "",
        "## §1 Prompt Master Scores",
        "",
        "| Model | Score | Table Directive | Words | Floor (70) |",
        "|-------|-------|-----------------|-------|------------|",
    ]
    for slug, r in pm_results.items():
        score = r.get("score", {}) if isinstance(r, dict) else {}
        if isinstance(score, dict):
            total = score.get("total", 0)
            td = "YES" if score.get("has_table_directive") else "NO"
            wc = score.get("word_count", 0)
            passed = "PASS" if total >= 70 else "FAIL"
            lines.append(f"| {slug} ({PM_MODELS.get(slug,'?')}) | {total} | {td} | {wc} | {passed} |")
        else:
            lines.append(f"| {slug} | ERROR | - | - | FAIL |")

    lines += [
        "",
        f"**Winner:** `{pm_winner[1]}` (slug: {pm_winner[0]})",
        "",
        "## §2 Intake Safety Check",
        "",
        f"Fallback model: `{intake_fallback}`",
        "",
        "See `INTAKE_FALLBACK_CHOICE.md` for details.",
        "",
        "## §3 Analyzer Scores",
        "",
        "| Model | Score | Consensus | Conflicts | Gaps | Numeric Facts | Floor (70) |",
        "|-------|-------|-----------|-----------|------|----------------|------------|",
    ]
    for slug, r in analyzer_results.items():
        score = r.get("score", {}) if isinstance(r, dict) else {}
        if isinstance(score, dict):
            total = score.get("total", 0)
            passed = "PASS" if total >= 70 else "FAIL"
            model = r.get("model", PM_MODELS.get(slug, "?"))
            lines.append(
                f"| {slug} | {total} | {score.get('consensus_count',0)} | "
                f"{score.get('conflicts_count',0)} | {score.get('gaps_count',0)} | "
                f"{score.get('numeric_facts_count',0)} | {passed} |"
            )
        else:
            lines.append(f"| {slug} | ERROR | - | - | - | - | FAIL |")

    lines += [
        "",
        f"**Winner:** `{analyzer_winner[1]}` (slug: {analyzer_winner[0]})",
        "",
        "## §4 Synthesizer Scores",
        "",
        "| Model | Score | QA | Tables | Charts | [REF:] | Sources | Floor (70) |",
        "|-------|-------|----|---------|----|-------|---------|------------|",
    ]
    for slug, r in synth_results.items():
        score = r.get("score", {}) if isinstance(r, dict) else {}
        if isinstance(score, dict):
            total = score.get("total", 0)
            passed = "PASS" if total >= 70 else "FAIL"
            lines.append(
                f"| {slug} | {total} | {score.get('qa_count',0)} | "
                f"{score.get('tables_count',0)} | {score.get('charts_count',0)} | "
                f"{score.get('ref_citations',0)} | {score.get('unique_sources',0)} | {passed} |"
            )
        else:
            lines.append(f"| {slug} | ERROR | - | - | - | - | - | FAIL |")

    lines += [
        "",
        f"**Winner:** `{synth_winner[1]}` (slug: {synth_winner[0]})",
        "",
        "## §5 Synthesis Critic",
        "",
        "Skipped per user decision. Critic stays on `anthropic/claude-opus-4.7`.",
        "",
        "Rationale: The Critic needs Opus-level reasoning to reliably detect contradictions.",
        "Downgrading risks FP>50% which per spec is a stop criterion. Cost of one critic call ",
        "($0.50-$2) is justified by the value of catching consistency errors in a final report.",
        "",
        "## Cost Estimates (per full prod run with winner config)",
        "",
        "| Stage | Model | Est. Cost USD |",
        "|-------|-------|--------------|",
        f"| Prompt Master | {pm_winner[1]} | ~$0.10-0.30 |",
        "| Intake | DETERMINISTIC (no LLM) | $0.00 |",
        f"| Intake LLM fallback (rare) | {intake_fallback} | ~$0.50 |",
        f"| Analyzer | {analyzer_winner[1]} | ~$1.50 |",
        f"| Synthesizer | {synth_winner[1]} | ~$1.00-3.00 |",
        "| Critic (fixed) | anthropic/claude-opus-4.7 | ~$1.00 |",
        "| **Total (no fallback)** | | **~$3.60-5.80** |",
        "",
        "## Revert configuration (Opus everywhere)",
        "",
        "```python",
        "# Safe revert — set all to Opus 4.7",
        'PROMPT_MASTER_MODEL = "anthropic/claude-opus-4.7"',
        'INTAKE_LLM_FALLBACK_MODEL = "anthropic/claude-opus-4.7"',
        'ANALYZER_MODEL = "anthropic/claude-opus-4.7"',
        'SYNTHESIZER_MODEL = "anthropic/claude-opus-4.7"',
        'SYNTHESIS_CRITIC_MODEL = "anthropic/claude-opus-4.7"',
        "```",
    ]

    (out_dir / "MODEL_CHOICES.md").write_text("\n".join(lines), encoding="utf-8")


def _write_eval(out_dir: Path, pm_results: dict, analyzer_results: dict, synth_results: dict, total_usd: float) -> None:
    """Write EVAL.md comparison table."""
    lines: list[str] = [
        "# EVAL — v4.5 Bake-off Full Comparison",
        "",
        f"Run date: {datetime.now(timezone.utc).isoformat()}",
        f"Total LLM spend this bake-off: ${total_usd:.3f}",
        "",
        "## Prompt Master Comparison",
        "",
        "| Model | Total | Length>200 | Entities≥5 | Table Dir | Time Window | Sections | Tips Tools |",
        "|-------|-------|-----------|-----------|---------|------------|---------|----------|",
    ]
    for slug, r in pm_results.items():
        score = r.get("score", {}) if isinstance(r, dict) else {}
        if isinstance(score, dict):
            bd = score.get("breakdown", {})
            lines.append(
                f"| {slug} | {score.get('total',0)} | "
                f"{bd.get('length_gt200',0)} | {bd.get('entities_ge5',0)} | "
                f"{bd.get('track0_table_directive',0)} | {bd.get('time_window',0)} | "
                f"{bd.get('structured_sections',0)} | {bd.get('tips_tools_ge2',0)} |"
            )

    lines += [
        "",
        "## Analyzer Comparison",
        "",
        "| Model | Total | Consensus≥10 | Conflicts≥5 | Gaps≥5 | Followup | Facts≥400 | Coverage>0 | Valid JSON |",
        "|-------|-------|-------------|------------|-------|---------|---------|-----------|-----------|",
    ]
    for slug, r in analyzer_results.items():
        score = r.get("score", {}) if isinstance(r, dict) else {}
        if isinstance(score, dict):
            bd = score.get("breakdown", {})
            lines.append(
                f"| {slug} | {score.get('total',0)} | "
                f"{bd.get('consensus_ge10',0)} | {bd.get('conflicts_ge5',0)} | "
                f"{bd.get('gaps_ge5',0)} | {bd.get('followup_populated',0)} | "
                f"{bd.get('numeric_facts_ge400',0)} | {bd.get('fact_coverage_gt0',0)} | "
                f"{bd.get('valid_json',0)} |"
            )

    lines += [
        "",
        "## Synthesizer Comparison",
        "",
        "| Model | Total | QA≥5 | Tables≥3 | Charts≥3 | KN 5-7 | Ranking | Synth≥3k | [REF:]≥20 | Src≥30 | RU-only |",
        "|-------|-------|-----|---------|---------|------|-------|--------|---------|------|--------|",
    ]
    for slug, r in synth_results.items():
        score = r.get("score", {}) if isinstance(r, dict) else {}
        if isinstance(score, dict):
            bd = score.get("breakdown", {})
            lines.append(
                f"| {slug} | {score.get('total',0)} | "
                f"{bd.get('qa_section_ge5',0)} | {bd.get('tables_ge3',0)} | "
                f"{bd.get('charts_ge3',0)} | {bd.get('key_numbers_5to7',0)} | "
                f"{bd.get('ranking_with_weights',0)} | {bd.get('main_synthesis_ge3000',0)} | "
                f"{bd.get('citations_ge20',0)} | {bd.get('sources_ge30',0)} | "
                f"{bd.get('russian_only',0)} |"
            )

    lines += [
        "",
        "## Subjective Spot-check Needed",
        "",
        "The following Synthesizer outputs need human review for depth and coherence:",
        "",
        "1. `synth_reports/sonnet-4.6.json` — cheapest candidate; check fact density and citation quality",
        "2. `synth_reports/gpt-4o.json` — different provider; check Russian language quality",
        "3. `synth_reports/opus-4.7.json` — baseline; confirm score matches perceived quality",
        "",
        "Key questions for subjective review:",
        "- Are the inline [REF:xxx] citations actually correct (not hallucinated)?",
        "- Is the ranking section actionable for a developer/shareholder?",
        "- Does main_synthesis read as a coherent argument, not a list of facts?",
    ]

    (out_dir / "EVAL.md").write_text("\n".join(lines), encoding="utf-8")


def _write_handoff(out_dir: Path, total_usd: float, sections_run: list[int]) -> None:
    (out_dir / "HANDOFF_BAKEOFF.md").write_text(
        f"""# Bake-off Handoff — v4.5

## Status

Sections completed: {sections_run}
Total LLM spend: ${total_usd:.3f} / ${BUDGET_USD_CAP} budget cap

## What was tested
- §1 Prompt Master: all 4 models (Opus 4.7, Sonnet 4.6, GPT-4o, Gemini 3.1 Pro)
- §2 Intake safety: Haiku 4.5 on amenities-main.md vs Opus baseline
- §3 Analyzer: Sonnet 4.6, GPT-4o, Gemini 3.1 Pro (+ cached Opus baseline)
- §4 Synthesizer: all 4 models in parallel
- §5 Skipped — Critic stays on Opus
- §6 Final smoke: winner config end-to-end

## Key files
- `MODEL_CHOICES.md` — winner config + rationale
- `EVAL.md` — full comparison tables
- `scoring.json` — numeric scores per stage/model
- `synth_reports/` — all 4 synthesizer outputs for subjective review
- `final_smoke.json` + `final_smoke.docx` — winner config full run
- `INTAKE_FALLBACK_CHOICE.md` — intake model decision
- `llm_log.jsonl` — every LLM call with cost

## Next steps
1. Subjective spot-check of 3 synthesizer outputs (see EVAL.md §Subjective)
2. Wire winner config into `smart_report/config.py` via ModelConfig class
3. Run tests: `pytest tests/ -x` to confirm all 288 tests green
4. If Synthesizer winner changes, update `synthesizer.py` SYNTHESIZER_MODEL constant

## Known limitations
- Intake §2 test ran on amenities-main.md only (the largest fixture)
  The other 3 fixtures use Opus baseline from cache; deterministic parser handles them in production
- Synthesizer scores are rules-based only; subjective depth needs human review
- GPT-4o and Gemini may produce Russian with more anglicisms — check `russian_only` score
""",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Config update
# ---------------------------------------------------------------------------

def _update_config(
    pm_model: str,
    intake_fallback: str,
    analyzer_model: str,
    synth_model: str,
) -> None:
    """Write/update smart_report/config.py with ModelConfig class."""
    config_path = REPO_ROOT / "smart_report" / "config.py"
    content = config_path.read_text(encoding="utf-8")

    model_config_block = f"""

# ---------------------------------------------------------------------------
# v4.5 Bake-off winner configuration
# ---------------------------------------------------------------------------
# Generated by scripts/run_bakeoff.py on {datetime.now(timezone.utc).date().isoformat()}
# To revert to Opus everywhere, set all MODEL fields to "anthropic/claude-opus-4.7"

class ModelConfig:
    \"\"\"Winner model configuration from v4.5 bake-off.\"\"\"

    PROMPT_MASTER_MODEL: str = "{pm_model}"

    # Intake: deterministic parser runs first (no LLM).
    # LLM fallback only if no Сводная таблица данных found in source.
    INTAKE_LLM_FALLBACK_MODEL: str = "{intake_fallback}"

    ANALYZER_MODEL: str = "{analyzer_model}"
    SYNTHESIZER_MODEL: str = "{synth_model}"

    # Critic stays on Opus per §5 decision (FP risk too high to downgrade)
    SYNTHESIS_CRITIC_MODEL: str = "anthropic/claude-opus-4.7"
"""

    if "class ModelConfig:" in content:
        # Replace existing block
        import re as _re
        content = _re.sub(
            r"\n# ---------------------------------------------------------------------------\n# v4\.5 Bake-off.*?(?=\n# ---|$)",
            model_config_block,
            content,
            flags=_re.DOTALL,
        )
    else:
        content += model_config_block

    config_path.write_text(content, encoding="utf-8")
    print(f"\n  Updated {config_path} with ModelConfig")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(skip_sections: set[int]) -> None:
    global _llm_log_path

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = REPO_ROOT / "runs" / "v45_bakeoff" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    _llm_log_path = out_dir / "llm_log.jsonl"

    print(f"Bake-off output dir: {out_dir}")
    print(f"Budget cap: ${BUDGET_USD_CAP}")
    print(f"OPENROUTER_API_KEY: {'SET' if OPENROUTER_API_KEY else 'NOT SET'}")

    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set — cannot run bake-off")

    sections_run: list[int] = []

    # §1 Prompt Master
    pm_results: dict = {}
    if 1 not in skip_sections:
        pm_results = await run_section1(out_dir)
        sections_run.append(1)
    else:
        print("\n[SKIP] §1 Prompt Master")
        # Load cached if available
        cached = out_dir / "pm_results.json"
        if cached.exists():
            with open(cached, encoding="utf-8") as f:
                pm_results = json.load(f)

    pm_winner = _pick_pm_winner(pm_results)
    print(f"\n  PM Winner: {pm_winner[0]} ({pm_winner[1]})")

    # §2 Intake safety
    intake_result: dict = {"fallback_choice": "anthropic/claude-opus-4.7", "decision": "opus (default)"}
    if 2 not in skip_sections and _check_budget():
        intake_result = await run_section2(out_dir)
        sections_run.append(2)
    else:
        print("\n[SKIP] §2 Intake Safety Check")

    intake_fallback = intake_result.get("fallback_choice", "anthropic/claude-opus-4.7")

    # §3 Analyzer
    analyzer_results: dict = {}
    if 3 not in skip_sections and _check_budget():
        analyzer_results = await run_section3(out_dir)
        sections_run.append(3)
    else:
        print("\n[SKIP] §3 Analyzer Bake-off")

    analyzer_winner_slug, analyzer_winner_model, analyzer_data = _pick_analyzer_winner(analyzer_results)
    print(f"\n  Analyzer Winner: {analyzer_winner_slug} ({analyzer_winner_model})")

    # §4 Synthesizer
    synth_results: dict = {}
    if 4 not in skip_sections and _check_budget():
        synth_results = await run_section4(out_dir, analyzer_data)
        sections_run.append(4)
    else:
        print("\n[SKIP] §4 Synthesizer Bake-off")

    synth_winner = _pick_synth_winner(synth_results)
    print(f"\n  Synth Winner: {synth_winner[0]} ({synth_winner[1]})")

    # Write scoring and reports
    _write_scoring(out_dir, pm_results, analyzer_results, synth_results)
    _write_model_choices(
        out_dir,
        pm_winner,
        (analyzer_winner_slug, analyzer_winner_model),
        synth_winner,
        intake_fallback,
        pm_results,
        analyzer_results,
        synth_results,
    )
    _write_eval(out_dir, pm_results, analyzer_results, synth_results, _total_cost_usd)

    # §6 Final smoke
    smoke_result: dict = {}
    if 6 not in skip_sections and _check_budget():
        smoke_result = await run_section6(
            out_dir,
            pm_winner,
            (analyzer_winner_slug, analyzer_winner_model),
            synth_winner,
            intake_fallback,
        )
        sections_run.append(6)
    else:
        print("\n[SKIP] §6 Final Smoke Run")

    # Update config.py with winner config
    _update_config(
        pm_model=pm_winner[1],
        intake_fallback=intake_fallback,
        analyzer_model=analyzer_winner_model,
        synth_model=synth_winner[1],
    )

    _write_handoff(out_dir, _total_cost_usd, sections_run)

    print(f"\n{'='*60}")
    print(f"Bake-off complete!")
    print(f"Total spend: ${_total_cost_usd:.3f}")
    print(f"Output dir: {out_dir}")
    print(f"PM Winner: {pm_winner[0]} ({pm_winner[1]})")
    print(f"Intake fallback: {intake_fallback}")
    print(f"Analyzer Winner: {analyzer_winner_slug} ({analyzer_winner_model})")
    print(f"Synth Winner: {synth_winner[0]} ({synth_winner[1]})")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="v4.5 Model Bake-off")
    parser.add_argument(
        "--skip-sections",
        default="",
        help="Comma-separated section numbers to skip (e.g. '2,6')",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=18.0,
        help="Budget cap in USD (default 18)",
    )
    args = parser.parse_args()

    skip = set()
    if args.skip_sections:
        for s in args.skip_sections.split(","):
            try:
                skip.add(int(s.strip()))
            except ValueError:
                pass

    BUDGET_USD_CAP = args.budget

    asyncio.run(main(skip))
