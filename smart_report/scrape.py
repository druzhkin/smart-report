"""Targeted page-scrape extractors for cells where Perplexity retrieval is lossy.

Perplexity is a good *search* tool but a poor *extraction* tool — it paraphrases
rather than pulling structured values from a known URL. When Planner already knows
which page holds the data (e.g. ЕРЗ's monthly developer ranking), we short-circuit
and fetch the page directly.

Backend: Jina Reader (https://r.jina.ai/) — free, no key, returns markdown with
JavaScript-rendered content. Firecrawl would be a paid upgrade path.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import httpx

from .config import REQUEST_TIMEOUT_S
from .io import append_jsonl
from .models import Finding

JINA_READER = "https://r.jina.ai/"


async def fetch_markdown(url: str, *, timeout: float | None = None) -> str:
    """Return the page rendered as markdown. Raises on HTTP error."""
    async with httpx.AsyncClient(timeout=timeout or REQUEST_TIMEOUT_S) as client:
        r = await client.get(f"{JINA_READER}{url}")
        r.raise_for_status()
        return r.text


# --- ERZ Moscow developer ranking -------------------------------------------

ERZ_MOSCOW_TOP_URL = "https://erzrf.ru/top-zastroyshchikov/moskva?topType=0"

# Pattern captures one developer row in the ERZ markdown table.
# Rows look like:
#   *   1 Место**0**[ПИК](.../pik-429726001...), г.Москва Строится, м² **2 378 878**С переносом срока 97 279 % 4.09 Уточнение срока, мес. 0.19 ... Доля в регионе 13.86% [5](...)
_ERZ_ROW = re.compile(
    r"\*\s+(?P<place>\d+)\s+Место\*\*[^*]*\*\*"
    r"\[(?P<name>[^\]]+)\]\((?P<url>[^)]+)\).*?"
    r"Строится,\s*м²\s*\*\*(?P<area_m2>[\d\s]+)\*\*"
    r"С\s+переносом\s+срока\s+(?P<delayed_m2>[\d\s]+)\s*%\s*(?P<delayed_pct>[\d.]+)"
    r"\s*Уточнение\s+срока,\s*мес\.\s*(?P<delay_months>[\d.]+)"
    r".*?Доля\s+в\s+регионе\s+(?P<share_pct>[\d.]+)%"
    r"\s*\[(?P<erz_rating>[\d.]+)\]",
    re.DOTALL,
)


def parse_erz_moscow_ranking(
    markdown: str, *, top_n: int = 10
) -> list[dict]:
    """Extract developer rows from the ERZ Moscow-top markdown.

    Returns one dict per developer: name, place, url, total_m2, delayed_m2,
    delayed_pct (% сроков переносят), delay_months (среднее уточнение),
    share_pct (доля региона), erz_rating (0–5 балл ЕРЗ).
    """
    out: list[dict] = []
    for m in _ERZ_ROW.finditer(markdown):
        if len(out) >= top_n:
            break
        g = m.groupdict()
        out.append(
            {
                "place": int(g["place"]),
                "name": g["name"].strip(),
                "url": g["url"].strip(),
                "total_m2": int(re.sub(r"\s+", "", g["area_m2"])),
                "delayed_m2": int(re.sub(r"\s+", "", g["delayed_m2"])),
                "delayed_pct": float(g["delayed_pct"]),
                "delay_months": float(g["delay_months"]),
                "share_pct": float(g["share_pct"]),
                "erz_rating": float(g["erz_rating"]),
            }
        )
    return out


def erz_rows_as_findings(rows: Iterable[dict]) -> list[dict]:
    """Convert ERZ developer rows into Finding-shaped dicts for Scout output.

    Each row becomes one finding where the 'headline' number is the % of ongoing
    m² with delayed completion — directly addresses 'скорость строительства'.
    Supplementary numbers (delay_months, erz_rating) surface in the claim text
    so Analyst can cite them.
    """
    findings = []
    for row in rows:
        claim = (
            f"{row['name']} (Москва, место {row['place']} по объёму): "
            f"{row['delayed_pct']}% строящихся м² с переносом срока "
            f"(строится {row['total_m2']:,} м², в переносе {row['delayed_m2']:,} м²); "
            f"среднее уточнение срока {row['delay_months']} мес.; "
            f"рейтинг ЕРЗ {row['erz_rating']}/5."
        ).replace(",", " ")
        findings.append(
            {
                "claim": claim,
                "number": f"{row['delayed_pct']}%",
                "source_url": ERZ_MOSCOW_TOP_URL,
                "source_type": "industry",
                "verbatim_quote": None,
            }
        )
    return findings


async def fetch_erz_moscow_developer_rows(top_n: int = 10) -> list[dict]:
    """End-to-end: pull the ЕРЗ Moscow ranking and return top-N developer rows."""
    md = await fetch_markdown(ERZ_MOSCOW_TOP_URL)
    return parse_erz_moscow_ranking(md, top_n=top_n)


# --- Generic URL extractor ---------------------------------------------------

def _extract_erzrf_moscow(md: str) -> list[dict]:
    rows = parse_erz_moscow_ranking(md, top_n=10)
    return erz_rows_as_findings(rows)


def _extract_generic(md: str, url: str) -> list[dict]:
    """Fallback: wrap the rendered markdown as a single 'other'-typed finding.

    Analyst will read the snippet and cite verbatim. Truncated to keep token
    budget bounded — Jina output can be many KB for content-heavy pages.
    """
    snippet = md.strip()[:2000]
    if not snippet:
        return []
    return [
        {
            "claim": snippet,
            "number": None,
            "source_url": url,
            "source_type": "other",
            "verbatim_quote": None,
        }
    ]


def _pick_parser(url: str):
    """Route a URL to a source-specific parser if we have one."""
    low = url.lower()
    if "erzrf.ru" in low and "top-zastroyshchikov" in low:
        return _extract_erzrf_moscow
    return None


async def extract_via_jina(
    target_urls: Iterable[str],
    *,
    focus: str | None = None,
    cell_id: str | None = None,
    log_dir: Path | None = None,
) -> list[Finding]:
    """Fetch each URL via Jina Reader and return Finding objects.

    For known sources (erzrf.ru Moscow ranking) a source-specific parser turns
    the rendered markdown into per-row structured findings. For anything else,
    the markdown is wrapped as a single 'other' finding so Analyst can still
    cite and quote from it — the extract strategy does not *require* a custom
    parser, it just benefits from one when structure is known.

    Failure-soft per URL: a fetch/parse exception is logged and skipped, the
    remaining URLs still contribute.
    """
    urls = [u for u in target_urls if u]
    findings: list[Finding] = []
    for url in urls:
        try:
            md = await fetch_markdown(url)
        except Exception as e:
            if log_dir is not None:
                append_jsonl(
                    log_dir / "llm_log.jsonl",
                    {
                        "kind": "extract_error",
                        "cell_id": cell_id,
                        "url": url,
                        "error": f"{type(e).__name__}: {e}",
                    },
                )
            continue

        parser = _pick_parser(url)
        dicts = parser(md) if parser else _extract_generic(md, url)

        if log_dir is not None:
            append_jsonl(
                log_dir / "llm_log.jsonl",
                {
                    "kind": "extract",
                    "cell_id": cell_id,
                    "url": url,
                    "parser": parser.__name__ if parser else "generic",
                    "focus": focus,
                    "n_findings": len(dicts),
                },
            )
        for d in dicts:
            try:
                findings.append(Finding(**d))
            except Exception:
                continue
    return findings
