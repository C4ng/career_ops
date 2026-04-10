from __future__ import annotations

import logging
import time
from unittest.mock import patch

import pytest

from app.utils.retry import retry_with_backoff


class _Transient(Exception):
    pass


class _Permanent(Exception):
    pass


def _retryable(exc: Exception) -> bool:
    return isinstance(exc, _Transient)


def test_retry_returns_value_on_first_success() -> None:
    result = retry_with_backoff(lambda: 42, max_attempts=3, retryable=_retryable)
    assert result == 42


def test_retry_succeeds_on_second_attempt() -> None:
    calls: list[int] = []

    def _fn() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise _Transient("boom")
        return "ok"

    with patch("app.utils.retry.time.sleep"):
        result = retry_with_backoff(_fn, max_attempts=3, retryable=_retryable, backoff_base_seconds=0.0)

    assert result == "ok"
    assert len(calls) == 2


def test_retry_raises_after_max_attempts() -> None:
    calls: list[int] = []

    def _always_fail() -> None:
        calls.append(1)
        raise _Transient("always fails")

    with patch("app.utils.retry.time.sleep"):
        with pytest.raises(_Transient, match="always fails"):
            retry_with_backoff(_always_fail, max_attempts=3, retryable=_retryable, backoff_base_seconds=0.0)

    assert len(calls) == 3


def test_retry_does_not_retry_permanent_errors() -> None:
    calls: list[int] = []

    def _fn() -> None:
        calls.append(1)
        raise _Permanent("hard stop")

    with pytest.raises(_Permanent, match="hard stop"):
        retry_with_backoff(_fn, max_attempts=3, retryable=_retryable)

    assert len(calls) == 1


def test_retry_exponential_backoff_durations() -> None:
    """Sleep intervals should double on each retry: 1s, 2s, 4s, …"""
    sleep_calls: list[float] = []

    def _always_fail() -> None:
        raise _Transient("fail")

    with patch("app.utils.retry.time.sleep", side_effect=lambda t: sleep_calls.append(t)):
        with pytest.raises(_Transient):
            retry_with_backoff(
                _always_fail,
                max_attempts=4,
                retryable=_retryable,
                backoff_base_seconds=1.0,
            )

    # 3 sleeps for 4 attempts: 1.0, 2.0, 4.0
    assert sleep_calls == [1.0, 2.0, 4.0]


def test_retry_logs_warning_on_retry(caplog: pytest.LogCaptureFixture) -> None:
    calls: list[int] = []

    def _fn() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise _Transient("flaky")
        return "done"

    with caplog.at_level(logging.WARNING, logger="app.utils.retry"):
        with patch("app.utils.retry.time.sleep"):
            retry_with_backoff(
                _fn,
                max_attempts=3,
                retryable=_retryable,
                operation_name="test_op",
                backoff_base_seconds=0.0,
            )

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("test_op" in msg for msg in warning_messages)


def test_retry_logs_give_up_warning_on_final_failure(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.utils.retry"):
        with patch("app.utils.retry.time.sleep"):
            with pytest.raises(_Transient):
                retry_with_backoff(
                    lambda: (_ for _ in ()).throw(_Transient("exhausted")),
                    max_attempts=2,
                    retryable=_retryable,
                    operation_name="give_up_op",
                    backoff_base_seconds=0.0,
                )

    messages = [r.message for r in caplog.records]
    assert any("give_up_op" in m for m in messages)
