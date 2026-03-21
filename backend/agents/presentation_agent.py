from __future__ import annotations

import asyncio
import json
import os

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, estimate_cost, get_model
from backend.pipeline.state import AgentState
from backend.utils.retry import llm_retry


class RendererError(Exception):
    pass


SYSTEM_PROMPT = """You are a presentation architect. Convert structured report data into a concise slide deck.

Input: executive_summary, key data points, report schema.
Do NOT use the full report text, only structured data.

Return JSON:
{
  "title": "Presentation Title",
  "slides": [
    {
      "title": "Slide Title",
      "bullets": ["Key point 1", "Key point 2"],
      "notes": "Speaker notes for this slide",
      "chart_ref": null or "chart_0.png"
    }
  ],
  "theme": "corporate"
}

Rules:
- Max 15 slides. First slide = title, last = key takeaways.
- Max 5 bullets per slide, each under 15 words.
- Include speaker notes with supporting data.
- Reference charts by filename where relevant."""

_GAMMA_BASE = "https://public-api.gamma.app/v1.0"
_GAMMA_POLL_INTERVAL = 5
_GAMMA_MAX_POLLS = 24


def _parse_slides_json(raw: str, report_title: str) -> dict:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed.setdefault("title", report_title or "Report")
            parsed.setdefault("slides", [])
            parsed.setdefault("theme", "corporate")
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict):
                parsed.setdefault("title", report_title or "Report")
                parsed.setdefault("slides", [])
                parsed.setdefault("theme", "corporate")
                return parsed
        except json.JSONDecodeError:
            logger.warning("Presentation JSON parse failed, using minimal fallback payload")

    return {
        "title": report_title or "Report",
        "slides": [
            {
                "title": "Executive Summary",
                "bullets": ["See attached report for details"],
                "notes": "Auto-generated fallback deck due to malformed LLM JSON.",
                "chart_ref": None,
            }
        ],
        "theme": "corporate",
    }


@llm_retry()
async def _generate_slide_json(data: str, model: str) -> str:
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": data},
                ],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _build_markdown(slides_json: dict) -> str:
    lines: list[str] = [f"# {slides_json.get('title', 'Report')}\n"]
    for slide in slides_json.get("slides", []):
        lines.append(f"## {slide.get('title', '')}")
        for bullet in slide.get("bullets", []):
            lines.append(f"- {bullet}")
        notes = slide.get("notes", "")
        if notes:
            lines.append(f"\n{notes}")
        lines.append("")
    return "\n".join(lines)


async def _gamma_create(markdown_text: str, out_path: str) -> str:
    if not settings.gamma_api_key:
        raise RendererError("GAMMA_API_KEY is not set")

    headers = {"X-API-KEY": settings.gamma_api_key}

    async with httpx.AsyncClient(timeout=30) as client:
        create_resp = await client.post(
            f"{_GAMMA_BASE}/generations",
            headers=headers,
            json={
                "inputText": markdown_text,
                "textMode": "condense",
                "format": "presentation",
                "numCards": 10,
                "exportAs": "pptx",
                "imageOptions": {"source": "noImages"},
            },
        )
        create_resp.raise_for_status()
        generation_data = create_resp.json()
        generation_id = generation_data.get("generationId")
        if not generation_id:
            raise RendererError(f"Gamma did not return generationId: {generation_data}")

    export_url: str | None = None
    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(_GAMMA_MAX_POLLS):
            await asyncio.sleep(_GAMMA_POLL_INTERVAL)
            poll_resp = await client.get(
                f"{_GAMMA_BASE}/generations/{generation_id}",
                headers=headers,
            )
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()
            status = poll_data.get("status")

            if status == "completed":
                export_url = poll_data.get("exportUrl")
                if not export_url:
                    raise RendererError(f"Gamma completed without exportUrl: {poll_data}")
                break
            if status == "failed":
                raise RendererError(f"Gamma generation failed: {poll_data}")

    if not export_url:
        raise RendererError("Gamma generation timed out")

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        download_resp = await client.get(export_url)
        download_resp.raise_for_status()
        with open(out_path, "wb") as file_obj:
            file_obj.write(download_resp.content)

    logger.info(f"Gamma PPTX saved: {out_path}")
    return out_path


def _build_input(state: AgentState) -> dict:
    report = state.get("report")
    master_prompt = state.get("master_prompt")

    data: dict = {
        "executive_summary": "",
        "key_data": [],
        "report_schema": {},
        "chart_refs": [],
    }

    if report:
        data["executive_summary"] = report.executive_summary
        data["key_data"] = [
            {"section": section.title, "source_count": len(section.sources)}
            for section in report.sections
        ]

    if master_prompt and master_prompt.report_schema:
        schema = master_prompt.report_schema
        data["report_schema"] = {
            "title_template": schema.title_template,
            "sections": [section.title for section in schema.sections],
            "constraints": schema.constraints,
        }

    chart_paths = state.get("chart_paths", [])
    data["chart_refs"] = [os.path.basename(path) for path in chart_paths]
    return data


@traceable(name="presentation_agent")
async def run_presentation(state: AgentState) -> dict:
    logger.info("Presentation agent started")
    report = state.get("report")
    if not report:
        logger.warning("No report for presentation")
        return {"current_agent": "presentation"}

    model = get_model(AgentTask.PRESENTATION)
    input_data = _build_input(state)
    input_json = json.dumps(input_data, default=str)

    raw = await _generate_slide_json(input_json, model)
    slides_json = _parse_slides_json(raw, report.title)

    cost = estimate_cost(AgentTask.PRESENTATION, len(input_json) // 4, len(raw) // 4)
    result: dict = {
        "messages": state.get("messages", []) + [
            {"role": "presentation", "content": raw}
        ],
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "presentation",
    }

    session_id = state.get("session_id", state.get("report_id", "default"))
    out_dir = os.path.join(settings.outputs_dir, session_id)
    os.makedirs(out_dir, exist_ok=True)

    slides_path = os.path.join(out_dir, "slides.json")
    with open(slides_path, "w", encoding="utf-8") as file_obj:
        json.dump(slides_json, file_obj, indent=2, ensure_ascii=False)

    if not settings.gamma_api_key:
        result["presentation_path"] = slides_path
        return result

    pptx_path = os.path.join(out_dir, "report.pptx")
    await _gamma_create(_build_markdown(slides_json), pptx_path)
    result["presentation_path"] = pptx_path
    result["final_report_paths"] = state.get("final_report_paths", []) + [pptx_path]
    return result
