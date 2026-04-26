"""Auto-DR: one-shot research-on-behalf for the chat UI.

When a user clicks "Заказать DR через Valyu" (or Tavily/Exa/Perplexity)
in the chat workspace, the frontend POSTs to /api/v4/sessions/{id}/auto-dr.
This module does the actual work: route to the right backend, run it,
return an UploadedMarkdown the endpoint then appends to
`session.source_reports` so the existing analyze→synthesize pipeline
picks it up exactly as if the analyst had pasted a Perplexity export.

Service catalog (mirrors the chat picker):
  valyu      — premium structured (sec.gov, fred, arxiv, pubmed). ~$0.10
  tavily     — cheap general web (basic) / advanced for regulatory. ~$0.005-0.020
  exa        — semantic similarity (papers/blogs). ~$0.005-0.020
  perplexity — LLM-based DR via OpenRouter `perplexity/sonar-pro`. ~$0.50-2

Copy-launch services (OpenAI ChatGPT DR, Claude, Gemini Deep Research)
do NOT route here — the frontend just copies the prompt and opens the
service in a new tab.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from smart_report.models import UploadedMarkdown

_logger = logging.getLogger(__name__)


AutoDRService = Literal["valyu", "tavily", "exa", "perplexity"]
SUPPORTED_SERVICES: tuple[AutoDRService, ...] = (
    "valyu", "tavily", "exa", "perplexity",
)


@dataclass
class AutoDRResult:
    """Output of run_auto_dr — what the endpoint feeds back to the session."""

    upload: UploadedMarkdown
    service: AutoDRService
    cost_usd: float
    cost_rub: float
    source_count: int
    notes: str = ""


class AutoDRError(RuntimeError):
    """Raised when the picked DR service failed (4xx, empty after retries, etc).

    The endpoint maps this to HTTP 502 — let the user pick another service.
    """


_USD_RUB_RATE: float = 75.4


async def run_auto_dr(
    service: AutoDRService,
    question: str,
    *,
    domain_hint: Optional[str] = None,
    max_results: int = 10,
) -> AutoDRResult:
    """Dispatch to the chosen service, return the markdown blob to ingest."""
    if service not in SUPPORTED_SERVICES:
        raise AutoDRError(f"unknown service {service!r}; allowed: {SUPPORTED_SERVICES}")
    if not question or not question.strip():
        raise AutoDRError("auto-dr requires a non-empty question/prompt")

    if service == "valyu":
        return await _run_search_backend(service, question, domain_hint, max_results)
    if service == "tavily":
        return await _run_search_backend(service, question, domain_hint, max_results)
    if service == "exa":
        return await _run_search_backend(service, question, domain_hint, max_results)
    if service == "perplexity":
        return await _run_perplexity_llm(question)
    raise AutoDRError(f"unreachable: service {service!r}")


# ---------------------------------------------------------------------------
# Search-backend services (valyu / tavily / exa)
# ---------------------------------------------------------------------------


async def _run_search_backend(
    service: AutoDRService,
    question: str,
    domain_hint: Optional[str],
    max_results: int,
) -> AutoDRResult:
    adapter = _make_adapter(service)
    result = await adapter.search(
        question, domain_hint=domain_hint, max_results=max_results,
    )
    if result.is_empty_or_error:
        raise AutoDRError(
            f"{service} returned empty/error: {result.error or 'no results'}"
        )
    md = _search_result_to_markdown(question, service, result, domain_hint)
    upload = UploadedMarkdown(
        filename=f"auto_dr_{service}.md",
        content=md,
        detected_tool="other",
        word_count=len(md.split()),
    )
    cost_usd = float(result.cost_usd or 0.0)
    return AutoDRResult(
        upload=upload,
        service=service,
        cost_usd=cost_usd,
        cost_rub=round(cost_usd * _USD_RUB_RATE, 4),
        source_count=len(result.sources),
        notes=(
            f"backend={service} latency_ms={result.latency_ms} "
            f"sources={len(result.sources)}"
        ),
    )


def _make_adapter(service: AutoDRService):
    """Construct the adapter for `service`. Raises AutoDRError on missing API key."""
    try:
        if service == "valyu":
            from .valyu_adapter import ValyuAdapter
            return ValyuAdapter()
        if service == "tavily":
            from .tavily_adapter import TavilyAdapter
            return TavilyAdapter()
        if service == "exa":
            from .exa_adapter import ExaAdapter
            return ExaAdapter()
    except RuntimeError as e:
        raise AutoDRError(f"{service} not configured: {e}") from e
    raise AutoDRError(f"no adapter for service {service!r}")


def _search_result_to_markdown(
    question: str, service: str, result, domain: Optional[str]
) -> str:
    """Render SearchResult as Perplexity-style markdown the v4 intake parses.

    Mirrors `pre_analyze_augment._valyu_results_to_markdown` so the
    intake parser sees a familiar shape regardless of which backend
    produced it.
    """
    lines = [
        f"# {service.title()} DeepSearch results — {question}",
        "",
        f"_Backend: {service}_"
        + (f" _(domain hint: {domain})_" if domain else ""),
        f"_Result count: {len(result.sources)}_",
        f"_Cost: ${result.cost_usd:.4f}_  _Latency: {result.latency_ms} ms_",
        "",
    ]
    for i, src in enumerate(result.sources, 1):
        title = src.title or "(untitled)"
        lines.append(f"## [{i}] {title}")
        meta = src.raw_metadata or {}
        if meta.get("publication_date") or meta.get("published_date"):
            pd = meta.get("publication_date") or meta.get("published_date")
            lines.append(f"_Published: {pd}_")
        if meta.get("score") is not None:
            lines.append(f"_Score: {meta['score']:.2f}_")
        if meta.get("valyu_source"):
            lines.append(f"_Dataset: {meta['valyu_source']}_")
        lines.append("")
        lines.append(src.snippet or "(no snippet)")
        lines.append("")
        lines.append(f"Citation: {src.url}")
        lines.append("")
    lines.append("## Sources")
    lines.append("")
    for i, src in enumerate(result.sources, 1):
        lines.append(f"{i}. {src.url}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Perplexity sonar-pro via OpenRouter (LLM-style DR)
# ---------------------------------------------------------------------------


_PERPLEXITY_MODEL = "perplexity/sonar-pro"
_PERPLEXITY_SYSTEM = (
    "You are a senior research analyst. The user will give you a research "
    "question. Produce a thorough, well-structured Markdown report with: "
    "(1) Executive summary; (2) Key findings (with inline [N] citations); "
    "(3) Supporting evidence broken down by sub-question; (4) Sources list "
    "with full URLs. Cite every factual claim. Prefer primary sources "
    "(regulators, filings, peer-reviewed papers, official press releases). "
    "Be specific with numbers and dates. The downstream pipeline will "
    "treat your Markdown as authoritative source material — do not invent "
    "data or URLs."
)


async def _run_perplexity_llm(question: str) -> AutoDRResult:
    """Call perplexity/sonar-pro via OpenRouter and wrap the markdown."""
    from smart_report.llm import call_json
    try:
        result = await call_json(
            role="auto_dr_perplexity",
            messages=[
                {"role": "system", "content": _PERPLEXITY_SYSTEM},
                {"role": "user", "content": question},
            ],
            model=_PERPLEXITY_MODEL,
            temperature=0.2,
        )
    except Exception as e:
        raise AutoDRError(f"perplexity sonar-pro failed: {type(e).__name__}: {e}") from e

    md = result.text.strip()
    if not md:
        raise AutoDRError("perplexity sonar-pro returned empty response")

    cost_rub = float(result.cost_rub or 0.0)
    cost_usd = cost_rub / _USD_RUB_RATE
    upload = UploadedMarkdown(
        filename="auto_dr_perplexity.md",
        content=md,
        detected_tool="perplexity",
        word_count=len(md.split()),
    )
    return AutoDRResult(
        upload=upload,
        service="perplexity",
        cost_usd=cost_usd,
        cost_rub=cost_rub,
        source_count=_count_citations(md),
        notes=f"backend=perplexity model={_PERPLEXITY_MODEL}",
    )


def _count_citations(md: str) -> int:
    """Rough citation count: number of `## ` headings under "## Sources" section.

    Used only for telemetry; if not parseable returns 0.
    """
    import re
    m = re.search(r"##\s*Sources?\s*$(.+)", md, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if not m:
        return 0
    sources_block = m.group(1)
    return len(re.findall(r"^\s*\d+\.\s", sources_block, re.MULTILINE))
