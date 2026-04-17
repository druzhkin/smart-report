"""Parallel corpus fetch — replaces per-scout fanout.

Architecture (variant E):
    goal + strategy  →  [Valyu fast, Perplexity Sonar DR, gpt-researcher]  →  Corpus

Each backend is an independent multi-agent research system that already does
decomposition, source discovery and summarisation internally. We run all three
in parallel, merge by URL/DOI and hand the unified Corpus to `corpus_mapper`.

Contract:
    fetch_corpus(goal, strategy, depth) -> Corpus

`strategy` is a 2-5 sentence description of what to search for — fed into
Valyu's `research_strategy` param, prepended to Sonar DR's user message, and
appended to gpt-researcher's query. Without a strategy, Valyu especially tends
to cover too broadly.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from config import perplexity_model_for, settings
from llm import account_provider

log = logging.getLogger("corpus_fetch")

BackendName = Literal["valyu", "sonar_dr", "gpt_researcher", "openai_dr", "gemini_dr"]


# ---------- models -------------------------------------------------------


class CorpusSource(BaseModel):
    url: str
    title: str
    full_text: str = ""
    excerpt: str | None = None
    backend: BackendName
    citation_count: int | None = None
    year: int | None = None
    is_peer_reviewed: bool = False
    word_count: int = 0
    language: str = "ru"


class Corpus(BaseModel):
    sources: list[CorpusSource] = Field(default_factory=list)
    synth_reports: dict[str, str] = Field(
        default_factory=dict,
        description="Backend → its own synthesized narrative report (valuable as-is for context)",
    )
    total_words: int = 0
    fetch_metadata: dict[str, Any] = Field(default_factory=dict)


# ---------- helpers ------------------------------------------------------


def _attr(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _word_count(text: str) -> int:
    return len((text or "").split())


def _dedup_by_url_and_doi(sources: list[CorpusSource]) -> list[CorpusSource]:
    """Deduplicate by canonical URL / DOI. Keeps the source with the longest full_text."""
    by_key: dict[str, CorpusSource] = {}
    for s in sources:
        key = (s.url or "").strip().lower().rstrip("/")
        if not key:
            continue
        # Normalise DOI URLs (http vs https, doi.org vs dx.doi.org) to one key
        for prefix in ("https://dx.doi.org/", "http://dx.doi.org/", "http://doi.org/"):
            if key.startswith(prefix):
                key = "https://doi.org/" + key[len(prefix):]
                break
        prev = by_key.get(key)
        if prev is None or len(s.full_text) > len(prev.full_text):
            by_key[key] = s
    return list(by_key.values())


# ---------- Valyu fast (primary) -----------------------------------------


def _valyu_collect_subtask_sources(result: Any) -> list[dict[str, str]]:
    """Walk result.messages to collect sub-task sources from tool-result entries.

    Valyu's DeepResearch runs multiple internal research sub-tasks. Each sub-task
    returns a tool-result in result.messages with shape:
        {"role": "tool", "content": [
            {"type": "tool-result", "toolName": "research",
             "output": {"type": "json", "value": {"sources": [
                {"source_id": "1", "title": "...", "url": "https://..."},
                ...
             ]}}}
        ]}

    These sub-task source dicts contain only {source_id, title, url} — no snippet.
    The top-level result.sources has the finalist citations with snippets; we merge
    both pools and let the snippet enrichment step fill in what's available.

    Returns list of {"url": str, "title": str} dicts (URL-deduped).
    """
    sub_sources: list[dict[str, str]] = []
    seen: set[str] = set()
    messages = _attr(result, "messages") or []
    for msg in messages:
        role = _attr(msg, "role") if not isinstance(msg, dict) else msg.get("role")
        if role != "tool":
            continue
        content = _attr(msg, "content") if not isinstance(msg, dict) else msg.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            item_type = item.get("type") if isinstance(item, dict) else _attr(item, "type")
            if item_type != "tool-result":
                continue
            output = item.get("output") if isinstance(item, dict) else _attr(item, "output")
            if not output:
                continue
            value = output.get("value") if isinstance(output, dict) else _attr(output, "value")
            if not isinstance(value, dict):
                continue
            sources_list = value.get("sources") or []
            for s in sources_list:
                url = (s.get("url") or "").strip() if isinstance(s, dict) else (_attr(s, "url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                title = (s.get("title") or url) if isinstance(s, dict) else (_attr(s, "title") or url)
                sub_sources.append({"url": url, "title": str(title)})
    return sub_sources


async def _fetch_valyu(goal: str, strategy: str, mode: str) -> tuple[list[CorpusSource], str]:
    """Valyu DeepResearch — multi-agent RU-aware web research with per-source snippets.

    `mode`: fast ($0.10) | standard ($0.50) | heavy ($2.50) | max ($15).

    Sources are collected from TWO locations in the result object:
    1. result.sources — finalist citations Valyu selected for its synthesis.
       These have title, url, snippet, word_count.
    2. result.messages[role=tool].content[type=tool-result].output.value.sources —
       intermediate sub-task sources found during research but not promoted to the
       final synthesis. These have only title + url (no snippet), but including them
       dramatically increases corpus coverage (e.g. 23 → 72 URLs on a simple query,
       and 54 → 184 sources on a real estate heavy-mode query).

    Both pools are deduplicated by URL before returning.
    """
    if not settings.valyu_api_key:
        return [], ""
    try:
        from valyu import Valyu  # lazy
    except ImportError:
        log.warning("valyu SDK missing")
        return [], ""

    def _run() -> Any:
        import os as _os
        _os.environ["VALYU_API_KEY"] = settings.valyu_api_key
        client = Valyu()
        create_kwargs: dict[str, Any] = {"query": goal, "mode": mode}
        if strategy:
            create_kwargs["research_strategy"] = strategy
        task = client.deepresearch.create(**create_kwargs)
        task_id = _attr(task, "deepresearch_id") or _attr(task, "id")
        if not task_id:
            # Surface creation failures (billing, auth, invalid mode) — the SDK returns
            # a DeepResearchCreateResponse with success=False and an error string.
            err = _attr(task, "error") or "unknown (no task_id and no error field)"
            success = _attr(task, "success")
            log.warning("valyu create failed: success=%r error=%r", success, err)
            return None
        return client.deepresearch.wait(task_id, poll_interval=5, max_wait_time=1800)

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        log.warning("valyu fetch failed: %s", exc)
        return [], ""

    # Normalise completed status — the SDK returns a DeepResearchStatus enum; compare
    # both the enum value string and the raw string for forward-compat.
    status_val = _attr(result, "status")
    status_str = str(status_val).lower() if status_val is not None else ""
    if not result or ("completed" not in status_str):
        log.warning("valyu: task did not complete (status=%r)", status_val)
        return [], ""

    # --- Pool 1: finalist citations (have snippet / word_count) ---
    sources_raw = _attr(result, "sources") or []
    # Build a URL→snippet index so we can enrich sub-task sources that happen to
    # share a URL with a finalist citation.
    finalist_by_url: dict[str, Any] = {}
    for s in sources_raw:
        url = (_attr(s, "url") or "").strip()
        if url:
            finalist_by_url[url] = s

    synth = str(_attr(result, "output") or "")
    out: list[CorpusSource] = []
    seen_urls: set[str] = set()

    def _add_source(url: str, title: str, snippet: str, word_count_hint: Any, year: Any) -> None:
        url = url.strip()
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        wc = _word_count(snippet) if not word_count_hint else int(word_count_hint) if isinstance(word_count_hint, (int, float)) else _word_count(snippet)
        out.append(CorpusSource(
            url=url,
            title=title or url,
            full_text=str(snippet)[:8000],
            excerpt=snippet[:500] if snippet else None,
            backend="valyu",
            year=year if isinstance(year, int) else None,
            word_count=wc,
        ))

    for s in sources_raw:
        url = (_attr(s, "url") or "").strip()
        snippet = str(_attr(s, "raw_content") or _attr(s, "content") or _attr(s, "snippet") or "")
        _add_source(
            url=url,
            title=str(_attr(s, "title") or url),
            snippet=snippet,
            word_count_hint=_attr(s, "word_count"),
            year=_attr(s, "year"),
        )
    direct_count = len(out)

    # --- Pool 2: sub-task sources from messages ---
    sub_sources = _valyu_collect_subtask_sources(result)
    for s in sub_sources:
        url = s["url"]
        # If a finalist entry exists for this URL, use its richer metadata.
        if url in finalist_by_url:
            continue  # already added above
        _add_source(
            url=url,
            title=s["title"],
            snippet="",       # sub-task entries have no snippet in the SDK response
            word_count_hint=None,
            year=None,
        )
    subtask_count = len(out) - direct_count

    # Cost accounting — Valyu returns actual cost in result.cost
    cost_raw = _attr(result, "cost")
    try:
        cost_usd = float(cost_raw) if cost_raw is not None else settings.valyu_usd_per_query
    except (TypeError, ValueError):
        cost_usd = settings.valyu_usd_per_query
    account_provider("valyu", cost_usd * settings.usd_to_credits)
    log.info(
        "valyu: direct_sources=%d sub_task_sources=%d dedup=%d synth=%d cost=$%.3f mode=%s",
        direct_count, subtask_count, len(out), len(synth), cost_usd, mode,
    )
    return out, synth


# ---------- Perplexity Sonar Deep Research -------------------------------


def _sonar_citation_windows(synth: str, cite_index: int, window: int = 500) -> str:
    """Extract context windows from synth around every [cite_index+1] marker.

    Perplexity sonar-deep-research embeds inline [n] markers (1-indexed) in the
    synthesized text. For citation at list index `cite_index` (0-indexed), we collect
    all ±`window`-char windows around each `[cite_index+1]` occurrence and concatenate
    them. This gives the mapper synthesized context about the source even though
    Sonar doesn't return raw page bodies.

    Returns a string capped at 4000 chars.
    """
    import re
    marker = f"[{cite_index + 1}]"
    # Use regex to find all occurrences reliably (handles edge-of-string)
    windows: list[str] = []
    for m in re.finditer(re.escape(marker), synth):
        start = max(0, m.start() - window)
        end = min(len(synth), m.end() + window)
        windows.append(synth[start:end])
    if not windows:
        return ""
    combined = "\n\n---\n\n".join(windows)
    return combined[:4000]


async def _fetch_sonar_dr(goal: str, strategy: str) -> tuple[list[CorpusSource], str]:
    """Perplexity Sonar — fresh web sources with snippets.

    Uses the active profile's `perplexity_model` (sonar / sonar-pro by default;
    `sonar-deep-research` is broken on Russian queries — it returns a `<think>`
    reasoning preamble with zero citations). Strategy is prepended to the user
    message.

    full_text enrichment: `search_results[].snippet` contains a 1-2 sentence
    extract from each source (title + url + date + snippet + source). We use it
    as full_text directly — no synthesis-window extraction needed. Fallback to
    inline [n] citation windows if a search_result has no snippet.
    """
    if not settings.perplexity_api_key:
        return [], ""
    import httpx

    model = perplexity_model_for()
    # Long/prescriptive strategies (>~1000ch) push sonar-deep-research into
    # refusal mode — it returns a <think> monologue about "cutoff limits" with
    # zero citations despite running searches. Cap strategy for DR to stay out
    # of that trap; other sonar variants tolerate longer context.
    strat_cap = 200 if "deep-research" in model else 3000
    strategy_trim = strategy[:strat_cap] if strategy else ""
    user_msg = goal if not strategy_trim else f"{goal}\n\nСтратегия поиска:\n{strategy_trim}"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a web-research agent. Always run web search and always "
                    "return at least 5 primary sources with concrete facts and numbers. "
                    "Never refuse the task and never caveat about knowledge cutoffs — "
                    "your search tool has live web access. Russian output if the query "
                    "is in Russian. Cite sources inline as [n]."
                ),
            },
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.perplexity_api_key}",
        "Content-Type": "application/json",
    }
    import time as _time
    t0 = _time.time()
    log.warning("sonar_dr: REQUEST model=%s goal_chars=%d strategy_chars=%d",
                model, len(goal), len(strategy))
    try:
        async with httpx.AsyncClient(timeout=600) as http:
            r = await http.post(
                "https://api.perplexity.ai/chat/completions",
                json=payload,
                headers=headers,
            )
            log.warning("sonar_dr: HTTP status=%d took=%.1fs", r.status_code, _time.time() - t0)
            if r.status_code != 200:
                body_preview = r.text[:500] if hasattr(r, "text") else ""
                log.warning("sonar_dr: non-200 body[:500]=%r", body_preview)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        log.warning("sonar_dr fetch failed (%s): %s took=%.1fs",
                    type(exc).__name__, exc, _time.time() - t0)
        return [], ""
    log.warning("sonar_dr: RESPONSE keys=%s usage=%s",
                sorted(data.keys()), data.get("usage"))

    synth_raw = (data.get("choices", [{}])[0].get("message") or {}).get("content", "") or ""
    # sonar-deep-research prepends <think>…</think> reasoning in English — strip it before
    # extracting citation windows so mapper sees only the final Russian report.
    import re as _re
    synth = _re.sub(r"<think>.*?</think>", "", synth_raw, flags=_re.DOTALL).strip()
    # Prefer search_results (has snippet/date/source); fall back to plain citations.
    search_results = data.get("search_results") or []
    citations = data.get("citations") or []
    log.warning(
        "sonar_dr: SHAPE synth_raw=%d synth=%d search_results=%d citations=%d first_sr=%r first_cit=%r",
        len(synth_raw), len(synth), len(search_results), len(citations),
        search_results[0] if search_results else None,
        citations[0] if citations else None,
    )
    if not search_results and not citations:
        # Dump raw response for inspection when both are empty
        try:
            import json as _json
            with open("_sonar_dr_empty_dump.json", "w", encoding="utf-8") as _f:
                _json.dump(data, _f, ensure_ascii=False, indent=2)
            log.warning("sonar_dr: dumped empty response to _sonar_dr_empty_dump.json")
        except Exception:
            pass

    out: list[CorpusSource] = []
    seen_urls: set[str] = set()

    # Primary: walk search_results — they carry snippets.
    for i, sr in enumerate(search_results):
        if not isinstance(sr, dict):
            continue
        url = (sr.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        title = sr.get("title") or url
        snippet = (sr.get("snippet") or "").strip()
        date = str(sr.get("date") or sr.get("last_updated") or "")
        # Supplement snippet with inline-[n] context windows from synth if available.
        # search_results order typically aligns with citations order (1-indexed [n]).
        window_ctx = _sonar_citation_windows(synth, i) if synth else ""
        parts = []
        if snippet:
            parts.append(snippet)
        if window_ctx:
            parts.append(window_ctx)
        full_text = "\n\n".join(parts)
        # Parse 4-digit year out of date if present (publish_date column absent; use year)
        year: int | None = None
        if date:
            import re as _re
            m = _re.search(r"\b(19|20)\d{2}\b", date)
            if m:
                try:
                    year = int(m.group(0))
                except ValueError:
                    year = None
        out.append(CorpusSource(
            url=url,
            title=title,
            full_text=full_text,
            excerpt=(snippet or full_text[:200]) or None,
            backend="sonar_dr",
            word_count=_word_count(full_text),
            year=year,
        ))

    # Fallback: any plain citations not already covered by search_results.
    for i, c in enumerate(citations):
        if isinstance(c, str):
            url, title = c.strip(), c
        elif isinstance(c, dict):
            url = (c.get("url") or "").strip()
            title = c.get("title") or url
        else:
            continue
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        full_text = _sonar_citation_windows(synth, i) if synth else ""
        out.append(CorpusSource(
            url=url,
            title=title,
            full_text=full_text,
            excerpt=full_text[:200] if full_text else None,
            backend="sonar_dr",
            word_count=_word_count(full_text),
        ))

    # Pick cost constant by model family.
    if "deep-research" in model:
        cost_usd = float(settings.perplexity_usd_sonar_dr)
        acct_key = "perplexity_dr"
    elif "pro" in model:
        cost_usd = float(settings.perplexity_usd_sonar_pro)
        acct_key = "perplexity_pro"
    else:
        cost_usd = float(settings.perplexity_usd_sonar)
        acct_key = "perplexity_sonar"
    account_provider(acct_key, cost_usd * settings.usd_to_credits)
    usage = data.get("usage") or {}
    log.info(
        "sonar_dr: model=%s sources=%d (search_results=%d citations=%d) synth=%d tokens=%s cost~$%.3f",
        model, len(out), len(search_results), len(citations), len(synth),
        usage.get("total_tokens", "?"), cost_usd,
    )
    return out, synth


# ---------- gpt-researcher (academic focus) ------------------------------


async def _fetch_gpt_researcher(goal: str, strategy: str) -> tuple[list[CorpusSource], str]:
    """gpt-researcher — academic-leaning web research via CORE/S2/DDG/Tavily.

    Accesses its research context directly (skip write_report) for per-source bodies.

    full_text enrichment: search_gptr.gpt_researcher_search builds a `text` corpus
    with per-source blocks in the format `[i] title — url\\nbody[:2000]`. For each
    citation at 1-based index `i` we extract the block starting at `[i] ` up to the
    next `[i+1] ` marker. This gives the mapper real scraped body text (not synthesis
    windows) for each source — filling the empty-string gap from the old code.
    """
    import re as _re

    try:
        from search_gptr import gpt_researcher_search
    except ImportError:
        log.warning("search_gptr module missing")
        return [], ""

    query = goal if not strategy else f"{goal}\n\n{strategy}"
    try:
        res = await gpt_researcher_search(query)
    except Exception as exc:
        log.warning("gpt_researcher fetch failed: %s", exc)
        return [], ""
    if res.get("fallback") == "gpt_researcher_failed":
        return [], ""

    synth = res.get("text") or ""
    citations = res.get("citations") or []

    # Build an index: citation 1-based number → body block extracted from synth.
    # search_gptr formats each source as "[i] title — url\nbody" separated by "---".
    # We split on "---" separators and look for blocks starting with "[i] ".
    block_by_index: dict[int, str] = {}
    if synth:
        # Split on the separator used in search_gptr.py corpus assembly
        blocks = _re.split(r"\n\n---\n\n", synth)
        for block in blocks:
            m = _re.match(r"^\[(\d+)\]\s", block.strip())
            if m:
                block_by_index[int(m.group(1))] = block.strip()

    out: list[CorpusSource] = []
    for i, c in enumerate(citations, 1):
        url = (c.get("url") or "").strip() if isinstance(c, dict) else ""
        if not url:
            continue
        title = (c.get("title") if isinstance(c, dict) else url) or url
        # Prefer the block we extracted (contains actual scraped body text).
        # Fall back to synth-window extraction if indexing didn't match.
        full_text = block_by_index.get(i, "")
        if not full_text and synth:
            full_text = _sonar_citation_windows(synth, i - 1)  # reuse window helper (0-indexed)
        full_text = full_text[:8000]
        out.append(CorpusSource(
            url=url,
            title=title,
            full_text=full_text,
            excerpt=full_text[:200] if full_text else None,
            backend="gpt_researcher",
            word_count=_word_count(full_text),
        ))
    log.info("gpt_researcher: cites=%d synth=%d enriched=%d", len(out), len(synth),
             sum(1 for s in out if s.full_text))
    return out, synth


# ---------- OpenAI Deep Research (Responses API, o3-deep-research) --------


async def _fetch_openai_dr(goal: str, strategy: str) -> tuple[list[CorpusSource], str]:
    """OpenAI Responses API with `o3-deep-research` — multi-step web research with citations.

    The model runs its own plan→search→synthesize loop server-side. We pass the
    strategy as a developer message (same role the API docs use for guidance) and
    the goal as the user message. Tools must include `web_search_preview`.
    """
    if not settings.openai_api_key:
        return [], ""
    try:
        from openai import AsyncOpenAI  # SDK already a project dep (llm.py)
    except ImportError:
        log.warning("openai SDK missing")
        return [], ""

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    inputs: list[dict[str, Any]] = []
    if strategy:
        inputs.append({"role": "developer", "content": [{"type": "input_text", "text": strategy}]})
    inputs.append({"role": "user", "content": [{"type": "input_text", "text": goal}]})

    try:
        resp = await client.responses.create(
            model=settings.openai_dr_model,
            input=inputs,
            tools=[{"type": "web_search_preview"}],
            reasoning={"summary": "auto"},
            background=False,
            timeout=1800,
        )
    except Exception as exc:
        log.warning("openai_dr fetch failed: %s", exc)
        return [], ""

    # Response structure: output is a list; final assistant message lives in output[-1]
    # with .content[0].text and .content[0].annotations (citations).
    synth = ""
    annotations: list[Any] = []
    try:
        for item in getattr(resp, "output", []) or []:
            if _attr(item, "type") == "message":
                for part in _attr(item, "content") or []:
                    text = _attr(part, "text")
                    if text:
                        synth = str(text)
                    for a in _attr(part, "annotations") or []:
                        annotations.append(a)
    except Exception as exc:
        log.warning("openai_dr: response parse failed: %s", exc)

    out: list[CorpusSource] = []
    seen: set[str] = set()
    for a in annotations:
        url = (_attr(a, "url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        title = _attr(a, "title") or url
        out.append(CorpusSource(
            url=url,
            title=str(title),
            full_text="",  # DR doesn't return raw bodies, just the synthesized report
            excerpt=None,
            backend="openai_dr",
        ))

    # Cost: prefer usage-based accounting when available.
    usage = getattr(resp, "usage", None)
    if usage is not None:
        in_tok = getattr(usage, "input_tokens", 0) or 0
        out_tok = getattr(usage, "output_tokens", 0) or 0
        # o3-deep-research ≈ $10/M in + $40/M out + per-search surcharge (rolled into fallback).
        cost_usd = (in_tok / 1_000_000) * 10.0 + (out_tok / 1_000_000) * 40.0 + 0.10
    else:
        cost_usd = settings.openai_dr_usd_per_query
    account_provider("openai_dr", cost_usd * settings.usd_to_credits)
    log.info("openai_dr: cites=%d synth=%d cost~$%.2f", len(out), len(synth), cost_usd)
    return out, synth


# ---------- Gemini Deep Research (gemini-2.5-pro + google_search grounding) ---


async def _fetch_gemini_dr(goal: str, strategy: str) -> tuple[list[CorpusSource], str]:
    """Gemini 2.5 Pro with Google Search grounding — closest API analog of the consumer
    Deep Research experience. We run a single grounded call; the model does multi-step
    search + synthesis internally via the search tool.
    """
    if not settings.gemini_api_key:
        return [], ""
    try:
        from google import genai  # `pip install google-genai`
        from google.genai import types as gen_types
    except ImportError:
        log.warning("google-genai SDK missing; `pip install google-genai`")
        return [], ""

    client = genai.Client(api_key=settings.gemini_api_key)

    prompt = goal
    if strategy:
        prompt = f"{goal}\n\nИсследовательская стратегия:\n{strategy}"

    def _run() -> Any:
        return client.models.generate_content(
            model=settings.gemini_dr_model,
            contents=prompt,
            config=gen_types.GenerateContentConfig(
                tools=[gen_types.Tool(google_search=gen_types.GoogleSearch())],
                temperature=0.2,
            ),
        )

    try:
        resp = await asyncio.to_thread(_run)
    except Exception as exc:
        log.warning("gemini_dr fetch failed: %s", exc)
        return [], ""

    synth = (getattr(resp, "text", None) or "").strip()

    # Grounding metadata exposes the web sources Gemini consulted.
    out: list[CorpusSource] = []
    seen: set[str] = set()
    try:
        candidates = getattr(resp, "candidates", None) or []
        for cand in candidates:
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
            chunks = getattr(gm, "grounding_chunks", None) or []
            for ch in chunks:
                web = getattr(ch, "web", None)
                if not web:
                    continue
                url = (getattr(web, "uri", "") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                title = getattr(web, "title", "") or url
                out.append(CorpusSource(
                    url=url,
                    title=str(title),
                    full_text="",
                    excerpt=None,
                    backend="gemini_dr",
                ))
    except Exception as exc:
        log.warning("gemini_dr: grounding parse failed: %s", exc)

    # Cost: usage metadata when available; otherwise fallback.
    usage = getattr(resp, "usage_metadata", None)
    if usage is not None:
        in_tok = getattr(usage, "prompt_token_count", 0) or 0
        out_tok = getattr(usage, "candidates_token_count", 0) or 0
        # gemini-2.5-pro ≈ $1.25/M in + $10/M out + $35/1000 grounded queries
        cost_usd = (in_tok / 1_000_000) * 1.25 + (out_tok / 1_000_000) * 10.0 + 0.035
    else:
        cost_usd = settings.gemini_dr_usd_per_query
    account_provider("gemini_dr", cost_usd * settings.usd_to_credits)
    log.info("gemini_dr: cites=%d synth=%d cost~$%.2f", len(out), len(synth), cost_usd)
    return out, synth


# ---------- public entry point ------------------------------------------


async def fetch_corpus(
    goal: str,
    strategy: str = "",
    backends: list[BackendName] | None = None,
    valyu_mode: str = "fast",
) -> Corpus:
    """Parallel fetch across enabled DR backends.

    Args:
        goal: the user's research question
        strategy: 2-5 sentence guide on what to search (domains × layers summary)
        backends: which to fetch from. Default: [valyu, sonar_dr, gpt_researcher]
        valyu_mode: fast | standard | heavy | max
    """
    backends = backends or ["valyu", "sonar_dr", "gpt_researcher"]

    task_map: dict[BackendName, asyncio.Task] = {}
    if "valyu" in backends and settings.use_valyu and settings.valyu_api_key:
        task_map["valyu"] = asyncio.create_task(_fetch_valyu(goal, strategy, valyu_mode))
    if "sonar_dr" in backends and settings.use_perplexity and settings.perplexity_api_key:
        task_map["sonar_dr"] = asyncio.create_task(_fetch_sonar_dr(goal, strategy))
    if "gpt_researcher" in backends and settings.use_gpt_researcher:
        task_map["gpt_researcher"] = asyncio.create_task(_fetch_gpt_researcher(goal, strategy))
    if "openai_dr" in backends and settings.use_openai_dr and settings.openai_api_key:
        task_map["openai_dr"] = asyncio.create_task(_fetch_openai_dr(goal, strategy))
    if "gemini_dr" in backends and settings.use_gemini_dr and settings.gemini_api_key:
        task_map["gemini_dr"] = asyncio.create_task(_fetch_gemini_dr(goal, strategy))

    if not task_map:
        log.warning("fetch_corpus: no backends enabled — returning empty corpus")
        return Corpus(fetch_metadata={"enabled_backends": []})

    results = await asyncio.gather(*task_map.values(), return_exceptions=True)

    all_sources: list[CorpusSource] = []
    synth_reports: dict[str, str] = {}
    meta: dict[str, Any] = {"enabled_backends": list(task_map.keys())}
    for (backend, _), res in zip(task_map.items(), results):
        if isinstance(res, Exception):
            log.warning("corpus fetch %s failed: %s", backend, res)
            meta[f"{backend}_success"] = False
            meta[f"{backend}_error"] = str(res)[:200]
            continue
        sources, synth = res
        all_sources.extend(sources)
        if synth:
            synth_reports[backend] = synth
        meta[f"{backend}_success"] = True
        meta[f"{backend}_sources"] = len(sources)
        meta[f"{backend}_synth_words"] = _word_count(synth)

    dedup = _dedup_by_url_and_doi(all_sources)
    total_words = sum(s.word_count for s in dedup) + sum(_word_count(s) for s in synth_reports.values())

    log.info(
        "corpus: backends=%s raw_sources=%d dedup=%d total_words=%d",
        list(task_map.keys()), len(all_sources), len(dedup), total_words,
    )

    return Corpus(
        sources=dedup,
        synth_reports=synth_reports,
        total_words=total_words,
        fetch_metadata=meta,
    )
