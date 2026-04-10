from __future__ import annotations

import imaplib
from unittest.mock import MagicMock, patch

import pytest

from app.services.email import _is_retryable_imap_error, connect_imap_mailbox
from app.models import LinkedInEmailConfig


# --- _is_retryable_imap_error ---


def test_is_retryable_on_os_error() -> None:
    assert _is_retryable_imap_error(OSError("connection refused"))


def test_is_retryable_on_connection_error() -> None:
    assert _is_retryable_imap_error(ConnectionError("reset"))


def test_is_retryable_on_timeout_error() -> None:
    assert _is_retryable_imap_error(TimeoutError("timeout"))


def test_is_retryable_on_imap_abort() -> None:
    assert _is_retryable_imap_error(imaplib.IMAP4.abort("server gone"))


def test_is_not_retryable_on_imap_error() -> None:
    # IMAP4.error (auth failure etc.) should NOT be retried
    assert not _is_retryable_imap_error(imaplib.IMAP4.error("bad credentials"))


def test_is_not_retryable_on_runtime_error() -> None:
    assert not _is_retryable_imap_error(RuntimeError("missing env var"))


# --- connect_imap_mailbox retry behaviour ---


_CONFIG = LinkedInEmailConfig(
    host="imap.example.com",
    port=993,
    mailbox="INBOX",
    username="user@example.com",
    password_env="EMAIL_PASSWORD",
    sender="alerts@linkedin.com",
)


def _make_imap_client() -> MagicMock:
    client = MagicMock(spec=imaplib.IMAP4_SSL)
    client.login.return_value = ("OK", [b"Logged in"])
    client.select.return_value = ("OK", [b"1"])
    return client


def test_connect_imap_succeeds_on_first_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PASSWORD", "secret")
    mock_client = _make_imap_client()

    with patch("imaplib.IMAP4_SSL", return_value=mock_client):
        client, authenticated, mailbox_selected = connect_imap_mailbox(_CONFIG)

    assert authenticated is True
    assert mailbox_selected is True


def test_connect_imap_retries_on_os_error_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PASSWORD", "secret")
    call_count = 0
    mock_client = _make_imap_client()

    def _imap4_ssl(*args, **kwargs):  # noqa: ANN001
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise OSError("connection refused")
        return mock_client

    with (
        patch("imaplib.IMAP4_SSL", side_effect=_imap4_ssl),
        patch("app.utils.retry.time.sleep"),
    ):
        client, authenticated, mailbox_selected = connect_imap_mailbox(_CONFIG, max_attempts=3)

    assert authenticated is True
    assert call_count == 2


def test_connect_imap_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PASSWORD", "secret")

    with (
        patch("imaplib.IMAP4_SSL", side_effect=OSError("always down")),
        patch("app.utils.retry.time.sleep"),
    ):
        with pytest.raises(OSError, match="always down"):
            connect_imap_mailbox(_CONFIG, max_attempts=2)


def test_connect_imap_does_not_retry_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PASSWORD", "wrong")
    call_count = 0

    def _imap4_ssl(*args, **kwargs):  # noqa: ANN001
        nonlocal call_count
        call_count += 1
        client = MagicMock()
        client.login.side_effect = imaplib.IMAP4.error("bad credentials")
        return client

    with patch("imaplib.IMAP4_SSL", side_effect=_imap4_ssl):
        with pytest.raises(imaplib.IMAP4.error):
            connect_imap_mailbox(_CONFIG, max_attempts=3)

    assert call_count == 1
