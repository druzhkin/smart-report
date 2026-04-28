"""Tests for llm._post_with_retry — Phase 3 Step 3.1 Task 1.4 (Run 1 finding 4).

Validates the retry shim added to defend against transient OpenRouter
failures: HTTP 200 with malformed JSON body (the exact failure mode of
Run 1 Q1 first attempt), ConnectError, and 5xx server errors. Also
asserts that 4xx errors (auth, payment, rate-limit) are NOT retried.

Mock-only — no network, no real httpx connections.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from smart_report.llm import (
    _BACKOFF_BASE_SEC,
    _MAX_TRANSPORT_ATTEMPTS,
    _post_with_retry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(status: int, body: str = "{}") -> httpx.Response:
    """Build a fake httpx.Response with given status and body."""
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return httpx.Response(status_code=status, content=body.encode(), request=request)


def _ok_response(payload: dict) -> httpx.Response:
    return _make_response(200, json.dumps(payload, ensure_ascii=False))


def _build_client_with_responses(responses: list):
    """Build a mock client where consecutive .post() calls return the
    sequenced responses (or raise the sequenced exceptions).

    Each item is either an httpx.Response (returned) or an Exception
    instance (raised when post() is awaited).
    """
    call_iter = iter(responses)
    client = MagicMock()

    async def post(url, headers=None, json=None):
        item = next(call_iter)
        if isinstance(item, BaseException):
            raise item
        return item

    client.post = AsyncMock(side_effect=post)
    return client


# ---------------------------------------------------------------------------
# Spec acceptance — 7 named tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retries_on_json_decode_error():
    """Run 1 finding 4 reproduction: HTTP 200 with malformed body on
    attempt 1, valid JSON on attempt 2 → success.
    """
    bad_resp = _make_response(200, "this is not json {[}")
    good_resp = _ok_response({"choices": [{"message": {"content": "ok"}}]})
    client = _build_client_with_responses([bad_resp, good_resp])

    with patch("smart_report.llm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        result = await _post_with_retry(
            client, "url", headers={}, json={}
        )
    assert result == {"choices": [{"message": {"content": "ok"}}]}
    assert client.post.await_count == 2  # one retry happened
    mock_sleep.assert_awaited_once_with(_BACKOFF_BASE_SEC)


@pytest.mark.asyncio
async def test_retries_on_connect_error():
    """Network blip on attempts 1 + 2, success on 3."""
    err = httpx.ConnectError("connection refused")
    good_resp = _ok_response({"ok": True})
    client = _build_client_with_responses([err, err, good_resp])

    with patch("smart_report.llm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        result = await _post_with_retry(client, "url", headers={}, json={})
    assert result == {"ok": True}
    assert client.post.await_count == 3
    # backoff: 1s, 2s
    assert mock_sleep.await_args_list[0].args == (_BACKOFF_BASE_SEC,)
    assert mock_sleep.await_args_list[1].args == (_BACKOFF_BASE_SEC * 2,)


@pytest.mark.asyncio
async def test_retries_on_5xx():
    """503 Service Unavailable on attempt 1, success on 2."""
    bad_resp = _make_response(503, "service unavailable")
    good_resp = _ok_response({"ok": True})
    client = _build_client_with_responses([bad_resp, good_resp])

    with patch("smart_report.llm.asyncio.sleep", new=AsyncMock()):
        result = await _post_with_retry(client, "url", headers={}, json={})
    assert result == {"ok": True}
    assert client.post.await_count == 2


@pytest.mark.asyncio
async def test_does_not_retry_on_4xx():
    """401 Unauthorized must raise immediately, not retry — auth
    failures don't get better with backoff.
    """
    bad_resp = _make_response(401, "unauthorized")
    client = _build_client_with_responses([bad_resp])

    with patch("smart_report.llm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        with pytest.raises(httpx.HTTPStatusError) as exc:
            await _post_with_retry(client, "url", headers={}, json={})
    assert exc.value.response.status_code == 401
    assert client.post.await_count == 1
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_does_not_retry_on_429():
    """429 Rate Limit must raise immediately. Backoff would only
    amplify rate-limiting; the caller (or operator) should slow down,
    not the retry loop.
    """
    bad_resp = _make_response(429, "rate limited")
    client = _build_client_with_responses([bad_resp])

    with patch("smart_report.llm.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(httpx.HTTPStatusError) as exc:
            await _post_with_retry(client, "url", headers={}, json={})
    assert exc.value.response.status_code == 429
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_max_retries_exhausted():
    """All transient failures in a row → raises the last exception."""
    err = httpx.ConnectError("persistent failure")
    client = _build_client_with_responses([err] * _MAX_TRANSPORT_ATTEMPTS)

    with patch("smart_report.llm.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(httpx.ConnectError):
            await _post_with_retry(client, "url", headers={}, json={})
    assert client.post.await_count == _MAX_TRANSPORT_ATTEMPTS


@pytest.mark.asyncio
async def test_backoff_timing_exponential():
    """Sleep durations between attempts must follow exponential pattern
    1s → 2s → 4s → … with N-1 sleeps for N attempts (last failure
    raises without sleeping)."""
    err = httpx.ConnectError("fail")
    client = _build_client_with_responses([err] * _MAX_TRANSPORT_ATTEMPTS)

    with patch("smart_report.llm.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        with pytest.raises(httpx.ConnectError):
            await _post_with_retry(client, "url", headers={}, json={})

    # N attempts → N-1 sleeps between them; the final failure raises
    # before any further sleep.
    expected_sleeps = _MAX_TRANSPORT_ATTEMPTS - 1
    assert mock_sleep.await_count == expected_sleeps
    durations = [call.args[0] for call in mock_sleep.await_args_list]
    expected_durations = [_BACKOFF_BASE_SEC * (2 ** i) for i in range(expected_sleeps)]
    assert durations == expected_durations
