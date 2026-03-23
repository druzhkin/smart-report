from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, estimate_cost, get_model
from backend.pipeline.state import AgentState
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry

SUPPORTED_CHART_TYPES = {"line", "bar", "pie", "treemap", "scatter", "waterfall"}

SYSTEM_PROMPT = """You are a data-visualization engineer.
You receive structured research findings and must produce self-contained Python scripts that use Plotly to create publication-quality charts.

Rules:
- Each chart is ONE standalone Python script.
- Use plotly.graph_objects (not plotly.express) for full control.
- Set chart dimensions 1200x800, white background, 300 DPI-equivalent.
- Use McKinsey blue palette: #003A70, #0071CE, #6CACE4, #9FC5E8, #BFD4E8, #D9E6F2.
- The script receives two CLI args: <chart_index> <output_dir>
- Save as PNG via fig.write_image(os.path.join(output_dir, f"chart_{chart_index}.png")).
- Allowed chart types: line, bar, pie, treemap, scatter, waterfall.
- For waterfall, use go.Waterfall. For treemap, use go.Treemap.
- All chart text (titles, labels, legends, annotations) MUST be in {chart_language}. Font: Arial.
- Do NOT use plt.show() or fig.show().
- RULE: fig.update_layout() ONLY keyword arguments.
- CORRECT: fig.update_layout(title=dict(text='My Title'))
- INCORRECT: fig.update_layout('My Title')

Return JSON:
{
  "charts": [
    {
      "chart_type": "bar",
      "title": "Market Share by Segment",
      "description": "Shows market share distribution",
      "python_code": "import plotly.graph_objects as go\\nimport os, sys\\n..."
    }
  ]
}"""


_VIZ_LANG_NAMES = {"ru": "Russian", "en": "English", "de": "German", "fr": "French", "es": "Spanish", "zh": "Chinese"}


def _has_plotly_image_runtime() -> bool:
    chrome_candidates = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome")
    if any(shutil.which(binary) for binary in chrome_candidates):
        return True
    return False


@llm_retry()
async def _generate_chart_specs(data_json: str, model: str, lang: str = "en") -> str:
    prompt = SYSTEM_PROMPT.replace("{chart_language}", _VIZ_LANG_NAMES.get(lang, lang))
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Generate Plotly charts for this data:\n\n{data_json}"},
        ],
        "temperature": 0.2,
        "max_tokens": 16384,
    }
    if supports_json_mode(model):
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _sanitize_chart_code(code: str) -> str:
    code = re.sub(
        r'fig\.update_layout\(\s*(["\'])(.*?)\1\s*,',
        lambda m: f'fig.update_layout(title={m.group(1)}{m.group(2)}{m.group(1)},',
        code,
    )
    code = re.sub(
        r'fig\.update_layout\(\s*(["\'])(.*?)\1\s*\)',
        lambda m: f'fig.update_layout(title={m.group(1)}{m.group(2)}{m.group(1)})',
        code,
    )
    return code


async def _execute_chart_code(
    code: str, chart_index: int, output_dir: str, timeout: int = 60
) -> str | None:
    code = _sanitize_chart_code(code)
    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            script_path = f.name

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            script_path,
            str(chart_index),
            output_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode != 0:
            logger.error(f"Chart {chart_index} failed (rc={proc.returncode}): {stderr.decode(errors='replace')[:500]}")
            return None

        png_path = os.path.join(output_dir, f"chart_{chart_index}.png")
        if os.path.exists(png_path):
            logger.info(f"Chart {chart_index} saved: {png_path}")
            return png_path

        logger.warning(f"Chart {chart_index}: script succeeded but PNG not found at {png_path}")
        return None

    except asyncio.TimeoutError:
        logger.error(f"Chart {chart_index} timed out after {timeout}s")
        return None
    except Exception as exc:
        logger.error(f"Chart {chart_index} execution error: {exc}")
        return None
    finally:
        if script_path and os.path.exists(script_path):
            os.unlink(script_path)


@traceable(name="viz_agent")
async def run_viz_agent(state: AgentState) -> dict:
    logger.info("Visualization agent started")
    if not _has_plotly_image_runtime():
        logger.warning("Visualization runtime is unavailable (Chrome/Chromium not found); skipping chart generation")
        return {"chart_paths": [], "current_agent": "viz_agent"}

    model = get_model(AgentTask.VISUALIZATION)
    session_id = state.get("session_id", state.get("report_id", "default"))

    charts_dir = os.path.join(settings.outputs_dir, session_id, "charts")
    os.makedirs(charts_dir, exist_ok=True)

    intake = state.get("intake_result")
    lang = intake.language if intake else "en"

    results = state.get("research_results", [])
    if not results:
        logger.warning("No research results for visualization")
        return {"chart_paths": [], "current_agent": "viz_agent"}

    data_for_viz = {
        "findings": [],
        "sources": [],
    }
    for result in results:
        data_for_viz["findings"].extend(result.findings)
        data_for_viz["sources"].extend(
            [{"title": source.title, "domain": source.domain} for source in result.sources]
        )

    data_json = json.dumps(data_for_viz, default=str)
    raw = await _generate_chart_specs(data_json, model, lang=lang)
    try:
        parsed = parse_llm_json(raw, context="viz_agent")
    except ValueError:
        logger.warning("Viz agent JSON parse failed, skipping charts")
        return {"chart_paths": [], "current_agent": "viz_agent"}

    charts = parsed.get("charts", [])
    charts = [chart for chart in charts if chart.get("chart_type") in SUPPORTED_CHART_TYPES]

    tasks = []
    for index, chart in enumerate(charts):
        code = chart.get("python_code", "")
        if code:
            tasks.append(_execute_chart_code(code, index, charts_dir))

    chart_paths: list[str] = []
    if tasks:
        executed = await asyncio.gather(*tasks, return_exceptions=True)
        for result in executed:
            if isinstance(result, str):
                chart_paths.append(result)

    cost = estimate_cost(AgentTask.VISUALIZATION, len(data_json) // 4, len(raw) // 4)
    logger.info(f"Viz agent produced {len(chart_paths)}/{len(charts)} charts")

    return {
        "chart_paths": chart_paths,
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "viz_agent",
    }
