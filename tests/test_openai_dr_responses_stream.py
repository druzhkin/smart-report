"""Unit tests for the direct-OpenAI Responses API streamer.

Mocks httpx.AsyncClient.stream so we don't hit the network. Covers:
  - delta extraction from response.output_text.delta events
  - cost_usd computation from response.completed.usage tokens
  - error event surfacing
  - prefix-stripping for OpenRouter-style model ids
  - missing OPENAI_API_KEY → RuntimeError
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from smart_report.sources.llm_deepresearch import (
    OPENAI_DR_TOKEN_PRICES_USD,
    _strip_openrouter_prefix,
    _stream_openai_responses,
)


def test_strip_openrouter_prefix_strips() -> None:
    assert _strip_openrouter_prefix("openai/o4-mini-deep-research") == "o4-mini-deep-research"


def test_strip_openrouter_prefix_noop_when_already_bare() -> None:
    assert _strip_openrouter_prefix("o3-deep-research") == "o3-deep-research"


def test_pricing_table_has_both_dr_models() -> None:
    assert "o4-mini-deep-research" in OPENAI_DR_TOKEN_PRICES_USD
    assert "o3-deep-research" in OPENAI_DR_TOKEN_PRICES_USD
    in_p, out_p = OPENAI_DR_TOKEN_PRICES_USD["o3-deep-research"]
    # output is more expensive than input for both models
    assert out_p > in_p > 0


# ---------------------------------------------------------------------------
# Stream parser tests — fake an SSE response with httpx mock
# ---------------------------------------------------------------------------


def _sse_lines(events: list[tuple[str, dict]]) -> list[str]:
    """Build SSE wire lines from (event_type, json_payload) pairs."""
    out: list[str] = []
    for et, payload in events:
        out.append(f"event: {et}")
        out.append(f"data: {json.dumps(payload)}")
        out.append("")  # blank line terminator
    return out


class _FakeResponse:
    def __init__(self, status_code: int, lines: list[str]) -> None:
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b""


class _FakeStreamCtx:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, *exc) -> None:
        pass


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:
        pass

    def stream(self, method: str, url: str, **kw) -> _FakeStreamCtx:  # noqa: ARG002
        return _FakeStreamCtx(self._response)


def _consume(stream_iter) -> list[dict]:
    async def _go() -> list[dict]:
        out = []
        async for chunk in stream_iter:
            out.append(chunk)
        return out
    return asyncio.run(_go())


def test_stream_parses_deltas_and_computes_cost(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    events = [
        ("response.created", {"id": "resp_1"}),
        ("response.output_text.delta", {"delta": "Hello"}),
        ("response.output_text.delta", {"delta": " world"}),
        ("response.completed", {
            "response": {"usage": {"input_tokens": 1000, "output_tokens": 5000}},
        }),
    ]
    fake = _FakeResponse(200, _sse_lines(events))
    with patch("httpx.AsyncClient", return_value=_FakeAsyncClient(fake)):
        chunks = _consume(_stream_openai_responses(
            "openai/o4-mini-deep-research",
            [{"role": "user", "content": "test"}],
        ))
    deltas = [c["delta"] for c in chunks if "delta" in c]
    costs = [c["cost_usd"] for c in chunks if "cost_usd" in c]
    assert deltas == ["Hello", " world"]
    assert len(costs) == 1
    # 1000 × $2/1M + 5000 × $8/1M = 0.002 + 0.04 = 0.042
    assert abs(costs[0] - 0.042) < 1e-9


def test_stream_skips_unknown_event_types(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    events = [
        ("response.in_progress", {}),
        ("response.output_item.added", {"item": {"type": "message"}}),
        ("response.output_text.delta", {"delta": "ok"}),
        ("response.completed", {"response": {"usage": {"input_tokens": 0, "output_tokens": 0}}}),
    ]
    fake = _FakeResponse(200, _sse_lines(events))
    with patch("httpx.AsyncClient", return_value=_FakeAsyncClient(fake)):
        chunks = _consume(_stream_openai_responses(
            "o3-deep-research",
            [{"role": "user", "content": "test"}],
        ))
    deltas = [c["delta"] for c in chunks if "delta" in c]
    assert deltas == ["ok"]


def test_stream_raises_on_error_event(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    events = [
        ("response.created", {"id": "resp_1"}),
        ("error", {"message": "rate limit exceeded"}),
    ]
    fake = _FakeResponse(200, _sse_lines(events))
    with patch("httpx.AsyncClient", return_value=_FakeAsyncClient(fake)):
        with pytest.raises(RuntimeError, match="rate limit exceeded"):
            _consume(_stream_openai_responses(
                "openai/o4-mini-deep-research",
                [{"role": "user", "content": "test"}],
            ))


def test_stream_raises_on_4xx_response(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    fake = _FakeResponse(401, [])
    with patch("httpx.AsyncClient", return_value=_FakeAsyncClient(fake)):
        with pytest.raises(RuntimeError, match=r"OpenAI Responses HTTP 401"):
            _consume(_stream_openai_responses(
                "openai/o4-mini-deep-research",
                [{"role": "user", "content": "test"}],
            ))


def test_stream_raises_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY not set"):
        _consume(_stream_openai_responses(
            "o3-deep-research",
            [{"role": "user", "content": "test"}],
        ))


def test_stream_skips_cost_when_model_unknown(monkeypatch) -> None:
    """Unknown model id → no cost yielded; deltas still flow."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    events = [
        ("response.output_text.delta", {"delta": "x"}),
        ("response.completed", {"response": {"usage": {"input_tokens": 100, "output_tokens": 100}}}),
    ]
    fake = _FakeResponse(200, _sse_lines(events))
    with patch("httpx.AsyncClient", return_value=_FakeAsyncClient(fake)):
        chunks = _consume(_stream_openai_responses(
            "openai/some-other-model",
            [{"role": "user", "content": "test"}],
        ))
    assert any("delta" in c for c in chunks)
    assert not any("cost_usd" in c for c in chunks)


# ---------------------------------------------------------------------------
# Cost reconciliation — _run_streaming_dr writes back actual cost on finalise
# ---------------------------------------------------------------------------


def test_finalise_reconciles_estimate_to_actual_completed(tmp_path, monkeypatch) -> None:
    """When the stream yields a real cost_usd, _finalise replaces the
    upfront estimate, updates total_cost_rub by the delta, and keeps the
    original estimate for audit."""
    from datetime import datetime, timezone
    from smart_report.models import V4Session
    from smart_report.sources.llm_deepresearch import _run_streaming_dr, _USD_RUB_RATE

    # Fake store backed by a dict, mimicking V4SessionStore minimal API.
    class _FakeStore:
        def __init__(self, sess: V4Session) -> None:
            self._s = sess
        def get(self, sid: str) -> V4Session:
            assert sid == self._s.session_id
            return self._s
        def update(self, sess: V4Session) -> None:
            self._s = sess

    sid = "rc-test-1"
    task_id = "task-rc-1"
    estimate_usd = 1.00
    estimate_rub = round(estimate_usd * _USD_RUB_RATE, 4)
    sess = V4Session(
        session_id=sid, raw_question="x", status="created",
        created_at=datetime.now(timezone.utc),
        total_cost_rub=estimate_rub,  # already debited at submit
        pending_dr_jobs=[{
            "task_id": task_id, "service": "perplexity", "mode": "deep",
            "model": "perplexity/sonar-deep-research",
            "cost_usd": estimate_usd, "cost_rub": estimate_rub,
            "submitted_at": 0.0, "state": "running",
            "partial_content": "", "partial_chars": 0,
            "last_progress_at": 0.0,
        }],
    )
    store = _FakeStore(sess)

    # Mock _stream_openrouter_chat to emit some text + a real cost chunk.
    async def _fake_stream(model_id, messages):  # noqa: ARG001
        yield {"delta": "hello "}
        yield {"delta": "world"}
        yield {"cost_usd": 1.83}  # actual was higher than the $1.00 estimate

    monkeypatch.setattr(
        "smart_report.sources.llm_deepresearch._stream_openrouter_chat",
        _fake_stream,
    )

    asyncio.run(_run_streaming_dr(
        task_id=task_id, question="q",
        model_id="perplexity/sonar-deep-research",
        service="perplexity", detected_tool="perplexity",
        session_id=sid, store=store,
    ))

    final = store.get(sid)
    # Job removed from pending on completion; result in source_reports
    assert all(j.get("task_id") != task_id for j in (final.pending_dr_jobs or []))
    assert any("perplexity" in u.filename for u in final.source_reports)
    # total_cost_rub was bumped by the delta: (1.83 - 1.00) × 95 = 78.85
    expected_actual_rub = round(1.83 * _USD_RUB_RATE, 4)
    assert abs(final.total_cost_rub - expected_actual_rub) < 0.01, (
        f"expected ≈ {expected_actual_rub}, got {final.total_cost_rub}"
    )


def test_finalise_keeps_estimate_when_no_cost_chunk(monkeypatch) -> None:
    """If stream completes without a cost_usd chunk (provider didn't
    report usage), keep the upfront estimate — don't zero out the bill."""
    from datetime import datetime, timezone
    from smart_report.models import V4Session
    from smart_report.sources.llm_deepresearch import _run_streaming_dr, _USD_RUB_RATE

    class _FakeStore:
        def __init__(self, sess: V4Session) -> None:
            self._s = sess
        def get(self, sid: str):
            return self._s
        def update(self, sess) -> None:
            self._s = sess

    sid = "rc-test-2"
    task_id = "task-rc-2"
    estimate_rub = round(0.50 * _USD_RUB_RATE, 4)
    sess = V4Session(
        session_id=sid, raw_question="x", status="created",
        created_at=datetime.now(timezone.utc),
        total_cost_rub=estimate_rub,
        pending_dr_jobs=[{
            "task_id": task_id, "service": "openai", "mode": "mini",
            "model": "openai/o4-mini-deep-research",
            "cost_usd": 0.50, "cost_rub": estimate_rub,
            "submitted_at": 0.0, "state": "running",
            "partial_content": "", "partial_chars": 0,
            "last_progress_at": 0.0,
        }],
    )
    store = _FakeStore(sess)

    async def _fake_stream(model_id, messages):  # noqa: ARG001
        yield {"delta": "no cost reported"}
        # no cost_usd chunk

    monkeypatch.setattr(
        "smart_report.sources.llm_deepresearch._stream_openrouter_chat",
        _fake_stream,
    )

    asyncio.run(_run_streaming_dr(
        task_id=task_id, question="q",
        model_id="openai/o4-mini-deep-research",
        service="openai", detected_tool="openai_dr",
        session_id=sid, store=store,
    ))

    final = store.get(sid)
    # Estimate untouched — total_cost_rub unchanged
    assert abs(final.total_cost_rub - estimate_rub) < 0.01
