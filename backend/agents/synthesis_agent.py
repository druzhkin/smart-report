from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from langsmith import traceable
from loguru import logger

from backend.pipeline.state import AgentState
from backend.schemas.quality import CitationStatus

LOW_AUTHORITY_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "reddit.com",
    "www.reddit.com",
    "t.me",
    "telegram.me",
    "medium.com",
    "www.medium.com",
    "vc.ru",
    "pikabu.ru",
    "dzen.ru",
    "zen.yandex.ru",
}

PRIMARY_SOURCE_HINTS = {
    "arxiv.org",
    "openai.com",
    "www.openai.com",
    "anthropic.com",
    "www.anthropic.com",
    "deepmind.google",
    "ai.google.dev",
    "github.com",
    "docs.python.org",
    "huggingface.co",
}


def _norm_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _claim_fingerprint(claim: str) -> str:
    return re.sub(r"\W+", " ", (claim or "").lower()).strip()


def _parse_domain(source_url: str, fallback: str = "") -> str:
    if fallback:
        return fallback.lower().strip()
    if not source_url:
        return ""
    try:
        return urlparse(source_url).netloc.lower().strip()
    except Exception:
        return ""


def _source_tier(domain: str) -> str:
    if not domain:
        return "unknown"
    if domain in PRIMARY_SOURCE_HINTS:
        return "primary"
    if domain in LOW_AUTHORITY_DOMAINS:
        return "low"
    return "secondary"


def _citation_factor(status: str) -> float:
    mapping = {
        CitationStatus.VERIFIED.value: 1.0,
        CitationStatus.PARTIAL.value: 0.75,
        CitationStatus.DEAD_LINK.value: 0.2,
        CitationStatus.FABRICATED.value: 0.0,
        "UNVERIFIED": 0.35,
    }
    return mapping.get(status, 0.35)


def _source_factor(tier: str) -> float:
    mapping = {"primary": 1.0, "secondary": 0.75, "unknown": 0.5, "low": 0.25}
    return mapping.get(tier, 0.5)


def _section_hint(claim: str, section_titles: list[str]) -> str:
    claim_tokens = set(re.findall(r"[a-zA-Zа-яА-Я0-9]+", (claim or "").lower()))
    if not claim_tokens or not section_titles:
        return ""
    ranked: list[tuple[int, str]] = []
    for title in section_titles:
        title_tokens = set(re.findall(r"[a-zA-Zа-яА-Я0-9]+", title.lower()))
        if not title_tokens:
            continue
        ranked.append((len(claim_tokens & title_tokens), title))
    ranked.sort(reverse=True)
    if ranked and ranked[0][0] > 0:
        return ranked[0][1]
    return ""


def _citation_status_by_url(state: AgentState) -> dict[str, str]:
    citation = state.get("citation_verification")
    if not citation:
        return {}

    statuses: dict[str, str] = {}
    for check in citation.checks:
        url = _norm_text(check.url)
        if url:
            statuses[url] = check.status.value if hasattr(check.status, "value") else str(check.status)
    return statuses


def _collect_section_titles(state: AgentState) -> list[str]:
    master_prompt = state.get("master_prompt")
    if not master_prompt or not master_prompt.report_schema:
        return []
    titles = [section.title for section in master_prompt.report_schema.sections if section.title]
    return titles[:24]


def _build_claim_table(state: AgentState) -> tuple[list[dict], dict[str, float]]:
    raw_items = list(state.get("evidence_items", []) or [])
    statuses = _citation_status_by_url(state)
    section_titles = _collect_section_titles(state)

    table: list[dict] = []
    best_by_fp: dict[str, dict] = {}
    for idx, raw in enumerate(raw_items, start=1):
        item = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else dict(raw)
        claim = _norm_text(str(item.get("claim", "")))
        if len(claim) < 20:
            continue

        source_url = _norm_text(str(item.get("source_url", "")))
        domain = _parse_domain(source_url, str(item.get("domain", "")))
        tier = _source_tier(domain)

        status = str(item.get("verification_status") or "").upper()
        if status not in {
            CitationStatus.VERIFIED.value,
            CitationStatus.PARTIAL.value,
            CitationStatus.DEAD_LINK.value,
            CitationStatus.FABRICATED.value,
        }:
            status = statuses.get(source_url, "UNVERIFIED")

        confidence = float(item.get("confidence", 0.0) or 0.0)
        score = round(confidence * _citation_factor(status) * _source_factor(tier), 4)

        usable = False
        if status == CitationStatus.VERIFIED.value:
            usable = score >= 0.4 and tier != "low"
        elif status == CitationStatus.PARTIAL.value:
            usable = score >= 0.55 and tier in {"primary", "secondary"}

        entry = {
            "id": item.get("id") or f"claim-{idx}",
            "claim": claim,
            "source_url": source_url,
            "source_title": _norm_text(str(item.get("source_title", ""))),
            "domain": domain,
            "source_tier": tier,
            "citation_status": status,
            "confidence": round(confidence, 4),
            "claim_score": score,
            "usable": usable,
            "section_hint": _section_hint(claim, section_titles),
            "snippet": _norm_text(str(item.get("snippet", "")))[:320],
        }

        fp = _claim_fingerprint(claim)
        prev = best_by_fp.get(fp)
        if prev is None or entry["claim_score"] > prev["claim_score"]:
            best_by_fp[fp] = entry

    table = list(best_by_fp.values())
    table.sort(key=lambda item: item["claim_score"], reverse=True)

    total = float(len(table))
    verified = float(sum(1 for row in table if row["citation_status"] == CitationStatus.VERIFIED.value))
    usable = float(sum(1 for row in table if row["usable"]))
    low_tier = float(sum(1 for row in table if row["source_tier"] == "low"))
    return table, {
        "total_claims": total,
        "verified_claims": verified,
        "usable_claims": usable,
        "verified_ratio": (verified / total) if total else 0.0,
        "usable_ratio": (usable / total) if total else 0.0,
        "low_authority_ratio": (low_tier / total) if total else 0.0,
    }


def _should_allow_recommendations(metrics: dict[str, float], state: AgentState) -> bool:
    citation = state.get("citation_verification")
    citation_passed = bool(citation and citation.passed)
    return (
        citation_passed
        and metrics["verified_claims"] >= 6
        and metrics["verified_ratio"] >= 0.62
        and metrics["low_authority_ratio"] <= 0.35
    )


def _is_synthesis_ready(metrics: dict[str, float], state: AgentState) -> tuple[bool, list[str]]:
    blocking: list[str] = []
    critique = state.get("research_critique_result")
    citation = state.get("citation_verification")

    if metrics["usable_claims"] < 4:
        blocking.append("Too few usable claims to produce a decision-grade synthesis.")
    if metrics["verified_claims"] < 3:
        blocking.append("Not enough verified claims for reliable conclusions.")
    if metrics["usable_ratio"] < 0.45:
        blocking.append("Usable claim ratio is too low; evidence base is too noisy.")
    if metrics["low_authority_ratio"] > 0.45:
        blocking.append("Source quality is too weak (high share of low-authority domains).")
    if not citation or not citation.passed:
        blocking.append("Citation verification did not pass quality threshold.")
    if critique and critique.overall_score < 0.55:
        blocking.append("Critique score remains below minimum synthesis threshold.")

    return (len(blocking) == 0), blocking


@traceable(name="synthesis_gate")
async def run_synthesis_gate(state: AgentState) -> dict:
    claim_table, metrics = _build_claim_table(state)
    ready, blocking_reasons = _is_synthesis_ready(metrics, state)
    allow_recommendations = _should_allow_recommendations(metrics, state)

    payload = {
        "metrics": metrics,
        "ready": ready,
        "allow_recommendations": allow_recommendations,
        "blocking_reasons": blocking_reasons[:8],
        "top_claims": [
            {
                "claim": row["claim"],
                "claim_score": row["claim_score"],
                "citation_status": row["citation_status"],
                "source_url": row["source_url"],
            }
            for row in claim_table[:12]
            if row.get("usable")
        ],
        "process_version": "synthesis-gate-v1",
    }

    logger.info(
        "Synthesis gate: ready={} usable={:.0f}/total={:.0f} verified={:.0f} allow_recs={}".format(
            ready,
            metrics["usable_claims"],
            metrics["total_claims"],
            metrics["verified_claims"],
            allow_recommendations,
        )
    )

    return {
        "claim_table": claim_table,
        "synthesis_payload": payload,
        "synthesis_ready": ready,
        "allow_recommendations": allow_recommendations,
        "messages": state.get("messages", [])
        + [{"role": "synthesis_gate", "content": json.dumps(payload, ensure_ascii=False)}],
        "current_agent": "synthesis_gate",
    }
