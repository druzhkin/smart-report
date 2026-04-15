"""Gamma API export: generates designer-grade presentations from a Report.

Docs: https://developers.gamma.app/
Auth: X-API-KEY header (NOT Bearer).
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from config import settings
from llm import account_provider
from models import Report

GAMMA_API_URL = "https://public-api.gamma.app/v1.0/generations"


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-API-KEY": settings.gamma_api_key,
    }


async def export_via_gamma(
    report: Report,
    export_as: str = "pptx",           # "pptx" | "pdf"
    tone: str = "professional",
    num_cards: int = 12,
    theme_id: str | None = None,
) -> dict[str, Any]:
    """Submit report to Gamma, poll until ready, return gamma_url + export_url."""
    if not settings.gamma_api_key:
        raise RuntimeError("GAMMA_API_KEY is not configured")

    content_md = build_gamma_content(report)

    payload: dict[str, Any] = {
        "inputText": content_md,
        "textMode": "generate",
        "format": "presentation",
        "numCards": num_cards,
        "exportAs": export_as,
        "textOptions": {"tone": tone, "language": "ru"},
        "cardOptions": {"dimensions": "16x9"},
    }
    if theme_id:
        payload["themeId"] = theme_id

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GAMMA_API_URL, json=payload, headers=_headers())
        resp.raise_for_status()
        result = resp.json()

        account_provider("gamma", settings.gamma_usd_per_generation * settings.usd_to_credits)

        return {
            "generation_id": result.get("generationId") or result.get("id"),
            "gamma_url": result.get("gammaUrl") or result.get("url"),
            "export_url": result.get("exportUrl"),
            "credits": result.get("credits"),
        }


async def poll_gamma_generation(generation_id: str) -> dict[str, Any]:
    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{GAMMA_API_URL}/{generation_id}", headers=_headers())
        if resp.status_code >= 400:
            return {"status": "pending"}
        data = resp.json()
        return {
            "status": data.get("status", "pending"),
            "gamma_url": data.get("gammaUrl") or data.get("url"),
            "export_url": data.get("exportUrl"),
        }


async def _poll_generation(
    client: httpx.AsyncClient, gen_id: str, max_wait: int = 600
) -> dict[str, Any]:
    for _ in range(max_wait // 3):
        await asyncio.sleep(3)
        resp = await client.get(f"{GAMMA_API_URL}/{gen_id}", headers=_headers())
        if resp.status_code >= 400:
            continue
        data = resp.json()
        status = data.get("status")
        if data.get("exportUrl") or status == "completed":
            return data
        if status in ("failed", "error"):
            raise RuntimeError(f"Gamma generation failed: {data}")
    raise TimeoutError(f"Gamma generation timed out after {max_wait}s")


def build_gamma_content(report: Report) -> str:
    """Render a compact markdown brief for Gamma: title, exec summary, numbers, top blocks, connections, gaps."""
    parts: list[str] = []

    parts.append(f"# {report.goal}\n")

    if report.exec_summary and report.exec_summary.goal_restate:
        parts.append("## Executive Summary\n")
        parts.append(f"{report.exec_summary.goal_restate}\n")
        if report.exec_summary.top_findings:
            parts.append("**Главные находки:**\n")
            for tf in report.exec_summary.top_findings[:5]:
                parts.append(f"- {tf.headline}")
            parts.append("")

    top_numbers: list[str] = []
    for block in report.blocks:
        for finding in (block.findings or []):
            if finding.has_numbers:
                top_numbers.append(f"- {finding.claim}")
    if top_numbers:
        parts.append("## Ключевые цифры\n")
        parts.extend(top_numbers[:8])
        parts.append("")

    header_by_cell = {h.cell: h for h in (report.block_headers or [])}

    def _priority_rank(block) -> int:
        header = header_by_cell.get(block.cell)
        if not header:
            return 0
        return (header.score_novelty or 0) + (header.score_concreteness or 0) + (header.score_applicability or 0)

    priority_blocks = sorted(report.blocks, key=_priority_rank, reverse=True)[:6]

    for block in priority_blocks:
        parts.append(f"## {block.cell}\n")
        header = header_by_cell.get(block.cell)
        if header and header.one_liner:
            parts.append(f"**{header.one_liner}**\n")
        summary = (block.summary or "")[:500]
        if summary:
            parts.append(summary + "\n")
        if block.gaps:
            parts.append(f"*Пробел: {block.gaps[0]}*\n")

    if report.connections:
        parts.append("## Неожиданные связи\n")
        icon_by_nature = {
            "paradox": "⚡",
            "causal_chain": "🔗",
            "unexpected_confirmation": "✓",
            "shared_variable": "◇",
        }
        for conn in report.connections[:3]:
            icon = icon_by_nature.get(conn.nature, "◇")
            parts.append(f"### {icon} {' ↔ '.join(conn.domains)}\n")
            parts.append(f"{conn.description}\n")
            if conn.novelty:
                parts.append(f"**Что нового:** {conn.novelty}\n")

    all_gaps: list[str] = []
    for block in report.blocks:
        if block.gaps:
            all_gaps.append(block.gaps[0])
    if all_gaps:
        parts.append("## Следующие шаги\n")
        for g in all_gaps[:5]:
            parts.append(f"- {g}")
        parts.append("")

    return "\n".join(parts)
