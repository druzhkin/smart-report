"""Contract tests for search._parse_or_fallback — pins the two regressions seen on
live sonar-pro smoke 05: (a) raw ```json fence leak into findings.claim,
(b) hallucinated source_urls overriding the Perplexity citations array."""

from __future__ import annotations

import json

from smart_report.search import _parse_or_fallback


def test_strips_json_code_fence() -> None:
    """Sonar-pro wraps its JSON body in ```json ... ``` — parser must strip."""
    text = "```json\n[\n  {\n    \"claim\": \"x\",\n    \"number\": \"1\",\n    \"source_url\": \"https://a.ru\",\n    \"source_type\": \"media\"\n  }\n]\n```"
    out = _parse_or_fallback(text, citations=["https://a.ru"])
    assert len(out) == 1
    assert out[0]["claim"] == "x"
    assert out[0]["source_url"] == "https://a.ru"


def test_bare_code_fence_also_works() -> None:
    text = "```\n[{\"claim\":\"y\",\"source_url\":\"https://b.ru\",\"source_type\":\"media\"}]\n```"
    out = _parse_or_fallback(text, citations=["https://b.ru"])
    assert len(out) == 1
    assert out[0]["claim"] == "y"


def test_hallucinated_url_replaced_by_citation() -> None:
    """Sonar invented a URL not in citations; parser must pin to a real citation."""
    body = json.dumps(
        [
            {
                "claim": "plausible claim",
                "number": "22",
                "source_url": "https://fake-site.example/fake/path",
                "source_type": "media",
            }
        ]
    )
    out = _parse_or_fallback(body, citations=["https://real-cite.ru/article"])
    assert out[0]["source_url"] == "https://real-cite.ru/article"
    assert out[0]["source_type"] == "other"  # downgraded because URL was hallucinated


def test_matching_url_kept_with_original_type() -> None:
    body = json.dumps(
        [
            {
                "claim": "c",
                "source_url": "https://real.ru/x",
                "source_type": "academic",
            }
        ]
    )
    out = _parse_or_fallback(body, citations=["https://real.ru/x"])
    assert out[0]["source_url"] == "https://real.ru/x"
    assert out[0]["source_type"] == "academic"


def test_fallback_on_pure_prose() -> None:
    out = _parse_or_fallback("just prose no json", citations=[])
    assert len(out) == 1
    assert out[0]["source_type"] == "other"
    assert out[0]["source_url"] == "https://perplexity.ai/"


def test_trailing_text_after_json_recoverable() -> None:
    text = "Here is the answer: [{\"claim\":\"z\",\"source_url\":\"https://c.ru\",\"source_type\":\"media\"}] done."
    out = _parse_or_fallback(text, citations=["https://c.ru"])
    assert len(out) == 1
    assert out[0]["claim"] == "z"


def test_think_block_stripped_then_json_parsed() -> None:
    """Sonar-pro leaks <think>...</think> reasoning blocks; recover JSON after."""
    text = (
        "<think>Let me think about this...</think>\n"
        '[{"claim":"real finding","source_url":"https://a.ru","source_type":"media"}]'
    )
    out = _parse_or_fallback(text, citations=["https://a.ru"])
    assert len(out) == 1
    assert out[0]["claim"] == "real finding"


def test_openended_think_falls_back_to_citation_salvage() -> None:
    """When response is only open-ended <think> but retrieval was real (many citations),
    salvage by emitting one placeholder per top citation instead of a raw-text blob."""
    text = "<think>I'm reasoning and didn't close the tag..."
    cites = [
        "https://metrium.ru/news/biznes-2024",
        "https://cbr.ru/statistics/mortgage",
        "https://erzrf.ru/publikacii/perenos-srokov",
        "https://dom.rf/reports/2024",
    ]
    out = _parse_or_fallback(text, citations=cites)
    # one per top citation (up to 5)
    assert len(out) == 4
    assert {f["source_url"] for f in out} == set(cites)
    for f in out:
        assert f["source_type"] == "other"
        assert "Retrieval returned prose" in f["claim"]


def test_think_only_no_citations_uses_prose_fallback() -> None:
    """With no citations, no salvage possible — keep legacy prose fallback."""
    text = "<think>open reasoning..."
    out = _parse_or_fallback(text, citations=[])
    assert len(out) == 1
    assert out[0]["source_url"] == "https://perplexity.ai/"
