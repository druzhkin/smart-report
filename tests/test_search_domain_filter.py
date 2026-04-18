"""Contract test: Planner's ScoutTask.target_sources must reach Perplexity payload
as `search_domain_filter`. This is the exact layer where v2 dropped the contract —
target_sources were formulated then silently discarded."""

from __future__ import annotations

import pytest

from smart_report.models import ScoutTask
from smart_report.scout import scout


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": '[]'}}],
            "citations": [],
        }


class _CapturingClient:
    """Captures the last JSON payload passed to post()."""

    captured: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str, *, headers: dict, json: dict) -> _FakeResponse:
        _CapturingClient.captured = json
        return _FakeResponse(json)


@pytest.mark.asyncio
async def test_target_sources_reach_perplexity_payload(monkeypatch) -> None:
    import httpx

    import smart_report.search as search_mod

    monkeypatch.setattr(search_mod, "PERPLEXITY_API_KEY", "test-key-nonempty")
    monkeypatch.setattr(httpx, "AsyncClient", _CapturingClient)
    _CapturingClient.captured = {}

    task = ScoutTask(
        cell_id="market:structure",
        query="HHI девелоперов бизнес-класса Москвы 2024",
        target_sources=["erzrf.ru", "dom.rf"],
    )
    await scout(task, mock=False, log_dir=None)

    sent = _CapturingClient.captured
    assert sent, "Perplexity payload was not captured — post() never reached"
    assert sent.get("search_domain_filter") == ["erzrf.ru", "dom.rf"], (
        f"target_sources lost on the way to Perplexity. Captured payload keys: {list(sent)}"
    )


@pytest.mark.asyncio
async def test_empty_target_sources_omits_filter(monkeypatch) -> None:
    """Empty list must NOT emit search_domain_filter — Perplexity rejects empty arrays."""
    import httpx

    import smart_report.search as search_mod

    monkeypatch.setattr(search_mod, "PERPLEXITY_API_KEY", "test-key-nonempty")
    monkeypatch.setattr(httpx, "AsyncClient", _CapturingClient)
    _CapturingClient.captured = {}

    task = ScoutTask(
        cell_id="market:structure",
        query="generic query",
        target_sources=[],
    )
    await scout(task, mock=False, log_dir=None)

    sent = _CapturingClient.captured
    assert sent, "post() never reached"
    assert "search_domain_filter" not in sent, (
        "empty target_sources must not send search_domain_filter"
    )


@pytest.mark.asyncio
async def test_org_names_are_filtered_out_domains_pass(monkeypatch) -> None:
    """Planner currently mixes org names and domains in target_sources.
    Only TLD-shaped strings must reach Perplexity's search_domain_filter — otherwise
    the API 400s (this is the actual bug that hit the first live smoke)."""
    import httpx

    import smart_report.search as search_mod

    monkeypatch.setattr(search_mod, "PERPLEXITY_API_KEY", "test-key-nonempty")
    monkeypatch.setattr(httpx, "AsyncClient", _CapturingClient)
    _CapturingClient.captured = {}

    task = ScoutTask(
        cell_id="construction:deadlines",
        query="перенос срока ЕРЗ",
        # Real v3 planner output mixed with a hand-added domain
        target_sources=["ЦБ РФ", "Frank RG", "ЕРЗ.РФ", "erzrf.ru", "https://dom.rf/reports"],
    )
    await scout(task, mock=False, log_dir=None)

    sent = _CapturingClient.captured
    assert sent, "post() never reached"
    assert sent.get("search_domain_filter") == ["erzrf.ru", "dom.rf"], (
        f"only TLD-shaped strings should propagate; got {sent.get('search_domain_filter')}"
    )
