from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.llm.client import _is_retryable_llm_error, request_structured_chat_completion
from app.services.llm.config import LLMServiceConfig


# --- _is_retryable_llm_error ---


def test_is_retryable_on_timeout() -> None:
    assert _is_retryable_llm_error(httpx.TimeoutException("timeout"))


def test_is_retryable_on_network_error() -> None:
    assert _is_retryable_llm_error(httpx.NetworkError("net err"))


def test_is_retryable_on_429() -> None:
    response = MagicMock()
    response.status_code = 429
    assert _is_retryable_llm_error(httpx.HTTPStatusError("rate limit", request=MagicMock(), response=response))


def test_is_retryable_on_503() -> None:
    response = MagicMock()
    response.status_code = 503
    assert _is_retryable_llm_error(httpx.HTTPStatusError("unavailable", request=MagicMock(), response=response))


def test_is_not_retryable_on_400() -> None:
    response = MagicMock()
    response.status_code = 400
    assert not _is_retryable_llm_error(httpx.HTTPStatusError("bad request", request=MagicMock(), response=response))


def test_is_not_retryable_on_401() -> None:
    response = MagicMock()
    response.status_code = 401
    assert not _is_retryable_llm_error(httpx.HTTPStatusError("unauthorized", request=MagicMock(), response=response))


def test_is_not_retryable_on_value_error() -> None:
    assert not _is_retryable_llm_error(ValueError("bad shape"))


# --- request_structured_chat_completion retry behaviour ---


_GOOD_RESPONSE = {
    "choices": [{"finish_reason": "stop", "message": {"content": '{"result": "ok"}'}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

_CONFIG = LLMServiceConfig(provider="openai", model="gpt-4o", api_key_env="OPENAI_API_KEY")


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_llm_call_succeeds_on_first_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mock_resp = _mock_response(_GOOD_RESPONSE)

    with patch("httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
        req, resp, content = request_structured_chat_completion(
            _CONFIG,
            system_prompt="sys",
            user_payload={"x": 1},
            response_schema={"type": "object"},
            schema_name="test",
        )

    assert content == '{"result": "ok"}'


def test_llm_call_retries_on_timeout_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    call_count = 0

    def _post(*args, **kwargs):  # noqa: ANN001
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.TimeoutException("timed out")
        return _mock_response(_GOOD_RESPONSE)

    with (
        patch("httpx.Client") as mock_client_cls,
        patch("app.utils.retry.time.sleep"),
    ):
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = _post
        _, _, content = request_structured_chat_completion(
            _CONFIG,
            system_prompt="sys",
            user_payload={"x": 1},
            response_schema={"type": "object"},
            schema_name="test",
            max_attempts=3,
        )

    assert content == '{"result": "ok"}'
    assert call_count == 2


def test_llm_call_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with (
        patch("httpx.Client") as mock_client_cls,
        patch("app.utils.retry.time.sleep"),
    ):
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = httpx.TimeoutException("always")
        with pytest.raises(httpx.TimeoutException):
            request_structured_chat_completion(
                _CONFIG,
                system_prompt="sys",
                user_payload={"x": 1},
                response_schema={"type": "object"},
                schema_name="test",
                max_attempts=2,
            )


def test_llm_call_does_not_retry_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    call_count = 0
    bad_resp = MagicMock(spec=httpx.Response)
    bad_resp.status_code = 400

    def _post(*args, **kwargs):  # noqa: ANN001
        nonlocal call_count
        call_count += 1
        raise httpx.HTTPStatusError("bad", request=MagicMock(), response=bad_resp)

    with patch("httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = _post
        with pytest.raises(httpx.HTTPStatusError):
            request_structured_chat_completion(
                _CONFIG,
                system_prompt="sys",
                user_payload={"x": 1},
                response_schema={"type": "object"},
                schema_name="test",
                max_attempts=3,
            )

    # No retry — should only have been called once
    assert call_count == 1
