from __future__ import annotations

import logging

import pytest

from app.services.llm.client import _choice_finish_reasons, _extract_content, _usage_summary


def test_usage_summary_extracts_token_fields() -> None:
    payload = {
        "usage": {
            "prompt_tokens": 123,
            "completion_tokens": 45,
            "total_tokens": 168,
            "prompt_tokens_details": {"cached_tokens": 10},
            "completion_tokens_details": {"reasoning_tokens": 4},
        }
    }

    assert _usage_summary(payload) == {
        "prompt_tokens": 123,
        "completion_tokens": 45,
        "total_tokens": 168,
        "prompt_tokens_details": {"cached_tokens": 10},
        "completion_tokens_details": {"reasoning_tokens": 4},
    }


# --- _extract_content ---


def test_extract_content_returns_content_from_valid_response() -> None:
    payload = {
        "choices": [
            {"finish_reason": "stop", "message": {"content": "hello world"}}
        ]
    }

    assert _extract_content(payload, schema_name="test") == "hello world"


def test_extract_content_raises_when_choices_key_missing() -> None:
    payload = {"id": "xyz", "model": "gemini-2.5-flash"}

    with pytest.raises(ValueError, match="has no choices"):
        _extract_content(payload, schema_name="my_schema")


def test_extract_content_raises_when_choices_is_empty_list() -> None:
    payload = {"choices": []}

    with pytest.raises(ValueError, match="has no choices"):
        _extract_content(payload, schema_name="my_schema")


def test_extract_content_raises_when_message_missing() -> None:
    payload = {"choices": [{"finish_reason": "stop"}]}

    with pytest.raises(ValueError, match="choices\\[0\\].message is missing or not a dict"):
        _extract_content(payload, schema_name="my_schema")


def test_extract_content_raises_when_content_is_none() -> None:
    payload = {"choices": [{"finish_reason": "stop", "message": {"content": None}}]}

    with pytest.raises(ValueError, match="content is None"):
        _extract_content(payload, schema_name="my_schema")


def test_extract_content_raises_when_content_is_not_string() -> None:
    payload = {"choices": [{"finish_reason": "stop", "message": {"content": {"nested": "dict"}}}]}

    with pytest.raises(ValueError, match="content is not a string"):
        _extract_content(payload, schema_name="my_schema")


def test_extract_content_logs_warning_for_non_stop_finish_reason(caplog) -> None:
    payload = {
        "choices": [
            {"finish_reason": "length", "message": {"content": "truncated output"}}
        ]
    }

    with caplog.at_level(logging.WARNING, logger="app.services.llm.client"):
        result = _extract_content(payload, schema_name="my_schema")

    assert result == "truncated output"
    warning = next(r for r in caplog.records if "non-stop reason" in r.message)
    assert warning.finish_reason == "length"


def test_extract_content_error_message_includes_schema_name() -> None:
    payload = {"choices": []}

    with pytest.raises(ValueError, match="important_schema"):
        _extract_content(payload, schema_name="important_schema")


# --- _choice_finish_reasons ---


def test_choice_finish_reasons_extracts_all_choice_reasons() -> None:
    payload = {
        "choices": [
            {"finish_reason": "stop"},
            {"finish_reason": "length"},
            {"message": {"content": "ignored missing reason"}},
        ]
    }

    assert _choice_finish_reasons(payload) == ["stop", "length", None]
