"""Gamma API integration for polished PPTX export.

Replaces the placeholder ``write_gamma_pptx_stub`` with a real generation
pipeline: ``FinalReport → input_text markdown → POST /v1.0/generations
→ poll → download exportUrl``. Generation typically takes 1-3 minutes;
docs cap at 5 min. We stop polling at 10 min to leave slack for the
ranges Gamma reports as "may take longer".

The HTTP layer wires this through the v4 long-task pattern (the same
pattern as analyze/synthesize) so the user-facing POST returns 202 in
<1s and the Cloudflare/Railway 100s proxy timeout never fires.

Environment:
    GAMMA_API_KEY — required; set via ``railway variables --set
    GAMMA_API_KEY=sk-gamma-...``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from ..models import FinalReport

log = logging.getLogger("smart_report.exporters.gamma_pptx")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_API_BASE = "https://public-api.gamma.app/v1.0"
_DEFAULT_TIMEOUT_S = 30.0
_POLL_INTERVAL_S = 5.0          # Gamma docs: "Use 5-second polling intervals"
_POLL_TIMEOUT_S = 600.0         # 10 min — covers the documented 1-3 min
                                # typical and the "may take longer" tail
_RATE_LIMIT_BACKOFF_S = 30.0    # Gamma docs: pause 30s on 429


class GammaError(Exception):
    """Raised on terminal Gamma API failures (auth, credits, generation fail)."""


# ---------------------------------------------------------------------------
# Input text builder — translates FinalReport into Gamma-friendly markdown
# ---------------------------------------------------------------------------


def build_input_text(report: FinalReport) -> str:
    """Render the FinalReport as markdown the Gamma generator can ingest.

    Gamma's chart/table generation works best with explicit data values
    in the input plus a clear chart-type hint in additionalInstructions
    (per the charts-and-structured-content guide). We surface every
    structured artefact (key_numbers_highlight, tables, ranking,
    callouts, qa_section) so Gamma can pattern-match them into slides
    rather than fabricating layouts from prose alone.
    """
    parts: list[str] = []

    parts.append(f"# {report.question.strip() or 'Аналитический отчёт'}\n")

    es = report.executive_summary
    if es.main_answer:
        parts.append("## Главный вывод\n")
        parts.append(es.main_answer.strip())
        parts.append("")

    if es.top_findings:
        parts.append("## Ключевые наблюдения\n")
        for finding in es.top_findings:
            parts.append(f"- {finding}")
        parts.append("")

    if report.key_numbers_highlight:
        parts.append("## Headline KPI\n")
        parts.append("| Метрика | Значение | Источник |")
        parts.append("|---|---|---|")
        for kn in report.key_numbers_highlight:
            src = (kn.source_ref or "").replace("|", " ").strip() or "—"
            parts.append(
                f"| {kn.label.replace('|', ' ')} | "
                f"{kn.value.replace('|', ' ')} | {src} |"
            )
        parts.append("")

    if report.qa_section:
        parts.append("## Ответы на под-вопросы\n")
        for qa in report.qa_section:
            parts.append(f"**{qa.question.strip()}**")
            parts.append("")
            parts.append(qa.answer.strip())
            parts.append("")

    if report.ranking:
        parts.append("## Приоритизация\n")
        parts.append("| Позиция | Название | Вес | Обоснование |")
        parts.append("|---|---|---|---|")
        for i, item in enumerate(report.ranking, start=1):
            weight = "" if item.weight is None else str(item.weight)
            rationale = (item.rationale or "").replace("|", " ").replace("\n", " ")
            parts.append(
                f"| {i} | {item.label.replace('|', ' ')} | {weight} | {rationale} |"
            )
        parts.append("")

    for tbl in report.tables:
        parts.append(f"## {tbl.title}\n")
        if tbl.columns and tbl.rows:
            parts.append("| " + " | ".join(c.replace("|", " ") for c in tbl.columns) + " |")
            parts.append("|" + "---|" * len(tbl.columns))
            for row in tbl.rows:
                # Pad / truncate cells so the markdown table parses
                cells = list(row[: len(tbl.columns)])
                while len(cells) < len(tbl.columns):
                    cells.append("")
                parts.append("| " + " | ".join(c.replace("|", " ") for c in cells) + " |")
        if tbl.caption:
            parts.append("")
            parts.append(f"_{tbl.caption}_")
        parts.append("")

    for chart in report.charts:
        parts.append(f"## {chart.title}\n")
        parts.append(f"_Тип графика: **{chart.chart_type}**_")
        parts.append("")
        # Surface data points explicitly so Gamma renders them; the
        # "labels + values" shape is the most common bar/line case
        # documented in their API guide.
        data = chart.data or {}
        labels = data.get("labels")
        values = data.get("values")
        if isinstance(labels, list) and isinstance(values, list):
            parts.append("| Категория | Значение |")
            parts.append("|---|---|")
            for label, val in zip(labels, values):
                parts.append(f"| {str(label).replace('|', ' ')} | {val} |")
        else:
            # Scatter / other shapes — dump as bullet list so Gamma at
            # least knows the data exists. Fallback path.
            for k, v in data.items():
                parts.append(f"- **{k}:** {v}")
        if chart.caption:
            parts.append("")
            parts.append(f"_{chart.caption}_")
        parts.append("")

    if report.callouts:
        parts.append("## Инсайты и риски\n")
        for c in report.callouts:
            tag = "💡" if c.kind == "insight" else (
                "⚠️" if c.kind == "warning" else "📌"
            )
            parts.append(f"### {tag} {c.title}")
            parts.append("")
            parts.append(c.body.strip())
            parts.append("")

    if report.main_synthesis:
        parts.append("## Главный синтез\n")
        parts.append(report.main_synthesis.strip())
        parts.append("")

    if report.consensus_section:
        parts.append("## Консенсус источников\n")
        parts.append(report.consensus_section.strip())
        parts.append("")

    if report.conflicts_section:
        parts.append("## Конфликты и их разрешение\n")
        parts.append(report.conflicts_section.strip())
        parts.append("")

    if report.gaps_filled_section:
        parts.append("## Пробелы (закрытые и оставшиеся)\n")
        parts.append(report.gaps_filled_section.strip())
        parts.append("")

    if report.all_sources:
        parts.append("## Источники\n")
        for s in report.all_sources[:80]:  # Gamma 100k-char cap; trim long tails
            line = f"- {s.title or s.url}"
            if s.url and s.url != s.title:
                line += f" ({s.url})"
            parts.append(line)

    text = "\n".join(parts).strip()
    # Gamma docs: inputText max 100,000 tokens (~400k chars). We aim well
    # under that so additionalInstructions + their internal padding fits.
    if len(text) > 350_000:
        text = text[:350_000] + "\n\n_(input truncated to fit Gamma's 100k-token cap)_"
    return text


_DEFAULT_INSTRUCTIONS = (
    "Создай профессиональную консалтинговую презентацию на русском "
    "языке. Используй таблицы для сравнительных данных; визуализируй "
    "числовые ряды и распределения как столбчатые / линейные / круговые "
    "диаграммы; выноси ключевые цифры на отдельные слайды как KPI; "
    "callout-блоки оформляй как highlighted-слайды с акцентом на инсайт. "
    "Аудитория — аналитики и руководство; тон — деловой, без воды."
)


# ---------------------------------------------------------------------------
# Async HTTP client — submit / poll / download
# ---------------------------------------------------------------------------


def _api_key() -> str:
    key = os.environ.get("GAMMA_API_KEY", "").strip()
    if not key:
        raise GammaError(
            "GAMMA_API_KEY env var is not set; export-gamma-pptx is unavailable"
        )
    return key


async def submit_generation(
    input_text: str,
    *,
    additional_instructions: str = _DEFAULT_INSTRUCTIONS,
    num_cards: int = 18,
    theme_id: str | None = None,
) -> str:
    """POST /generations — returns the generationId for polling."""
    payload: dict[str, Any] = {
        "inputText": input_text,
        "textMode": "preserve",  # we already structured the markdown
        "format": "presentation",
        "exportAs": "pptx",
        "cardSplit": "auto",
        "numCards": num_cards,
        "additionalInstructions": additional_instructions,
        "textOptions": {
            "amount": "detailed",
            "tone": "профессиональный аналитический",
            "language": "ru",
        },
        "imageOptions": {
            "source": "noImages",  # data-heavy report; suppress AI imagery
        },
        "cardOptions": {"dimensions": "16x9"},
    }
    if theme_id:
        payload["themeId"] = theme_id

    headers = {
        "X-API-KEY": _api_key(),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_S) as client:
        r = await client.post(
            f"{_API_BASE}/generations", json=payload, headers=headers
        )
    if r.status_code == 401:
        raise GammaError("Gamma API rejected the API key (401)")
    if r.status_code == 402:
        raise GammaError("Gamma account has no credits remaining (402)")
    if r.status_code >= 400:
        raise GammaError(
            f"Gamma /generations returned {r.status_code}: {r.text[:500]}"
        )
    body = r.json()
    gen_id = body.get("generationId")
    if not gen_id:
        raise GammaError(
            f"Gamma /generations response missing generationId: {body!r}"
        )
    return gen_id


async def get_generation_status(gen_id: str) -> dict[str, Any]:
    """GET /generations/{id} — returns the status payload as-is."""
    headers = {"X-API-KEY": _api_key()}
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_S) as client:
        r = await client.get(
            f"{_API_BASE}/generations/{gen_id}", headers=headers
        )
    if r.status_code == 404:
        raise GammaError(f"Gamma generation {gen_id} not found (404)")
    if r.status_code == 401:
        raise GammaError("Gamma API rejected the API key (401)")
    if r.status_code == 429:
        # Caller decides whether to retry; we surface the rate-limit signal
        raise GammaError("Gamma API rate limit hit (429)")
    if r.status_code >= 400:
        raise GammaError(
            f"Gamma /generations/{gen_id} returned {r.status_code}: {r.text[:500]}"
        )
    return r.json()


async def poll_until_done(
    gen_id: str,
    *,
    interval_s: float = _POLL_INTERVAL_S,
    timeout_s: float = _POLL_TIMEOUT_S,
) -> dict[str, Any]:
    """Poll until status is `completed` or `failed`. Raises GammaError on
    failure or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    backoff = interval_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            status = await get_generation_status(gen_id)
        except GammaError as e:
            if "429" in str(e):
                await asyncio.sleep(_RATE_LIMIT_BACKOFF_S)
                continue
            raise

        # Status field shape varies in the docs (sometimes a dict,
        # sometimes a string). Normalise.
        raw_status = status.get("status")
        if isinstance(raw_status, dict):
            phase = raw_status.get("name") or raw_status.get("state") or ""
        else:
            phase = str(raw_status or "")
        phase_norm = phase.lower()

        if phase_norm in {"completed", "complete", "done", "succeeded"}:
            return status
        if phase_norm in {"failed", "error", "errored"}:
            err = status.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise GammaError(f"Gamma generation {gen_id} failed: {msg or 'no detail'}")

        await asyncio.sleep(backoff)

    raise GammaError(
        f"Gamma generation {gen_id} did not finish within {timeout_s:.0f}s"
    )


async def download_pptx(export_url: str, dest: Path) -> Path:
    """Stream the PPTX bytes from Gamma's export URL to *dest*."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        async with client.stream("GET", export_url) as resp:
            if resp.status_code >= 400:
                raise GammaError(
                    f"Gamma exportUrl returned {resp.status_code}: "
                    f"{(await resp.aread())[:300]!r}"
                )
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
    return dest


async def generate_pptx(
    report: FinalReport,
    dest: Path,
    *,
    num_cards: int = 18,
    theme_id: str | None = None,
) -> Path:
    """End-to-end: submit → poll → download. Returns the local file path.

    Designed to be invoked by the long-task background loop. Logs each
    phase boundary so a hang on either side (Gamma slow, network slow)
    surfaces in Railway logs within a few seconds.
    """
    input_text = build_input_text(report)
    log.info(
        "gamma-pptx submitting generation len_input=%d num_cards=%d",
        len(input_text), num_cards,
    )
    print(
        f"[gamma-pptx] submitting len={len(input_text)} cards={num_cards}",
        flush=True,
    )
    gen_id = await submit_generation(
        input_text, num_cards=num_cards, theme_id=theme_id
    )
    log.info("gamma-pptx generationId=%s submitted; polling", gen_id)
    print(f"[gamma-pptx] generationId={gen_id} polling…", flush=True)

    status = await poll_until_done(gen_id)
    export_url = status.get("exportUrl") or status.get("export_url")
    if not export_url:
        raise GammaError(
            f"Gamma generation {gen_id} completed but exportUrl missing: "
            f"{status!r}"
        )
    log.info("gamma-pptx generationId=%s ready; downloading", gen_id)
    print(f"[gamma-pptx] generationId={gen_id} ready, downloading", flush=True)

    out = await download_pptx(export_url, dest)
    log.info(
        "gamma-pptx generationId=%s downloaded to %s (%d bytes)",
        gen_id, out, out.stat().st_size,
    )
    print(
        f"[gamma-pptx] DONE generationId={gen_id} file={out} bytes={out.stat().st_size}",
        flush=True,
    )
    return out
