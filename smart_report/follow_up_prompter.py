"""Generate targeted follow-up DR prompts for evidence gaps (v4.5 Phase 2 Step 2.4).

After gap_detector.detect_gaps emits an EvidenceGap list, this module
calls an LLM (Haiku 4.5 by default) to formulate a focused research
prompt for each actionable gap (severity == critical or moderate).
The analyst then runs these prompts in a Deep Research tool and feeds
the results back through /upload-reports for a second analyze pass.

Minor-severity gaps (1 authoritative source out of the threshold of 2)
are intentionally skipped — adding a third citation is rarely worth a
full second DR run, and the bar would otherwise raise to "must always
iterate" which defeats the cap.

Tolerant by design: HTTP errors, malformed JSON, schema-invalid items
all return an empty (or partial) list rather than crash. Caller treats
empty as "no follow-up prompts to surface" without blocking the flow.
"""

from __future__ import annotations

import json as _json
import logging as _logging
from typing import TYPE_CHECKING

from .io import extract_json
from .llm import call_json
from .models import FollowUpPrompt

if TYPE_CHECKING:
    from .models import EvidenceGap


_log = _logging.getLogger(__name__)


# Haiku 4.5 — cheap-tier verified in Step 2.2 acceptance.
DEFAULT_FOLLOW_UP_MODEL = "anthropic/claude-haiku-4.5"


FOLLOW_UP_SYSTEM_PROMPT = """You are a research analyst helping the user formulate targeted follow-up Deep Research prompts to close evidence gaps in an existing analysis.

For each evidence gap below, write ONE focused research prompt that:
- States the specific question to investigate (use the gap's sub_question text as anchor)
- Lists 2-4 priority source types from the gap's suggested_search_directions
- Stays concise (200-400 chars per prompt) — DR tools work better with focused prompts than bloated paragraphs
- Recommends one DR tool from this set (suggested_dr_tool):
    * perplexity_dr — best for Russian sources, RU regulatory / official statistics, Russian RE topics
    * chatgpt_dr — best for English-language tech / SaaS / international comparisons / academic
    * claude_research — best for long analytical chains needing multi-source synthesis
- Stay in the language of the original analyst query (Russian → Russian prompt; English → English prompt)

Anti-patterns:
- Restating the original query verbatim (the prompt should narrow, not duplicate)
- Vague meta-instructions ("find more information about ...")
- Asking for opinions or speculation (DR tools work best on retrievable facts)

Output STRICT JSON. No prose outside JSON. No markdown fences (but the parser tolerates them via extract_json):

{
  "follow_up_prompts": [
    {
      "sub_question_id": "sq2",
      "prompt_text": "...the prompt the analyst will paste into the DR tool...",
      "suggested_dr_tool": "perplexity_dr",
      "rationale": "Why this prompt + why this tool, in 1-2 sentences."
    }
  ]
}

If the gap list is empty or no gaps are actionable, return {"follow_up_prompts": []}.
"""


_ACTIONABLE_SEVERITIES = {"critical", "moderate"}


async def generate_follow_up_prompts(
    gaps: list["EvidenceGap"],
    original_query: str,
    *,
    model: str = DEFAULT_FOLLOW_UP_MODEL,
    mock: bool = False,
) -> list[FollowUpPrompt]:
    """Batch one LLM call to generate FollowUpPrompts for actionable gaps.

    Returns an empty list when:
      - gaps is empty
      - no gaps are actionable (only minor-severity entries)
      - mock=True
      - HTTP / JSON / schema failure (graceful degradation)

    Single LLM call covers all gaps in one pass — Haiku at 200-tokens-system
    + ~100-tokens-per-gap is well under $0.05 even for 5 gaps.
    """
    if not gaps:
        return []
    actionable = [g for g in gaps if g.severity in _ACTIONABLE_SEVERITIES]
    if not actionable:
        return []
    if mock:
        return []

    user_message = _build_user_message(original_query, actionable)

    try:
        result = await call_json(
            role="follow_up_prompter",
            messages=[
                {"role": "system", "content": FOLLOW_UP_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            model=model,
            temperature=0.3,
            response_format={"type": "json_object"},
            max_tokens=2500,
        )
    except Exception as e:  # pragma: no cover — network / HTTP edge
        _log.warning("follow-up prompter LLM call failed: %r — returning empty", e)
        return []

    return _parse_follow_up_output(result.text, actionable_ids={g.sub_question_id for g in actionable})


def _build_user_message(original_query: str, actionable: list["EvidenceGap"]) -> str:
    """Pack the actionable gap list into a compact user message."""
    truncated_query = original_query.strip()
    if len(truncated_query) > 600:
        truncated_query = truncated_query[:597] + "…"
    parts = [
        "Original analyst query:",
        truncated_query,
        "",
        "Evidence gaps to address (one follow-up prompt per gap, "
        "preserve sub_question_id verbatim):",
        "",
    ]
    for g in actionable:
        parts.append(f"- sub_question_id: {g.sub_question_id}")
        parts.append(f"  severity: {g.severity}")
        parts.append(f"  question: {g.sub_question_text}")
        parts.append(f"  reason: {g.reason}")
        if g.suggested_search_directions:
            sources_csv = ", ".join(g.suggested_search_directions)
            parts.append(f"  suggested_source_types: {sources_csv}")
        parts.append("")
    parts.append("Generate the JSON object now.")
    return "\n".join(parts)


def _parse_follow_up_output(
    raw: str, *, actionable_ids: set[str]
) -> list[FollowUpPrompt]:
    """Convert raw LLM output into validated FollowUpPrompt list.

    Drops entries with unknown sub_question_id, missing prompt_text,
    or any pydantic-validation failure. Empty list signals "unusable
    output" to the caller without crashing.
    """
    try:
        data = extract_json(raw)
    except (ValueError, _json.JSONDecodeError) as e:
        _log.warning("follow-up JSON parse failed: %r", e)
        return []
    if not isinstance(data, dict):
        return []
    raw_items = data.get("follow_up_prompts")
    if not isinstance(raw_items, list):
        return []

    prompts: list[FollowUpPrompt] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("sub_question_id") or "").strip()
        text = str(item.get("prompt_text") or "").strip()
        if not sid or not text:
            continue
        if sid not in actionable_ids:
            # LLM hallucinated an id we didn't ask about — skip
            continue
        tool_raw = str(item.get("suggested_dr_tool") or "perplexity_dr").strip()
        if tool_raw not in {"perplexity_dr", "chatgpt_dr", "claude_research"}:
            tool_raw = "perplexity_dr"  # default per spec
        try:
            prompts.append(
                FollowUpPrompt(
                    sub_question_id=sid,
                    prompt_text=text,
                    suggested_dr_tool=tool_raw,  # type: ignore[arg-type]
                    rationale=str(item.get("rationale") or "").strip(),
                )
            )
        except Exception as e:
            _log.warning("follow-up sub_question rejected: %r — %r", item, e)
            continue
    return prompts
