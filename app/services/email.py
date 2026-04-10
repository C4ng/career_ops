from __future__ import annotations

import imaplib
import logging
import os

from app.models import LinkedInEmailConfig
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


def _is_retryable_imap_error(exc: Exception) -> bool:
    """Return True for transient IMAP connection errors worth retrying."""
    return isinstance(exc, (OSError, ConnectionError, TimeoutError, imaplib.IMAP4.abort))


def load_email_password(config: LinkedInEmailConfig) -> str:
    password = os.environ.get(config.password_env)
    if not password:
        raise RuntimeError(f"Environment variable {config.password_env} is not set")
    return password


def connect_imap_mailbox(
    config: LinkedInEmailConfig,
    max_attempts: int = 3,
) -> tuple[imaplib.IMAP4_SSL, bool, bool]:
    password = load_email_password(config)

    def _connect() -> tuple[imaplib.IMAP4_SSL, bool, bool]:
        client = imaplib.IMAP4_SSL(config.host, config.port)
        login_status, _ = client.login(config.username, password)
        authenticated = login_status == "OK"
        select_status, _ = client.select(config.mailbox)
        mailbox_selected = select_status == "OK"
        return client, authenticated, mailbox_selected

    return retry_with_backoff(
        _connect,
        max_attempts=max_attempts,
        retryable=_is_retryable_imap_error,
        operation_name="imap_connect",
        log=logger,
    )


def close_imap_client(client: imaplib.IMAP4_SSL | None) -> None:
    if client is None:
        return
    try:
        client.close()
    except Exception:
        pass
    try:
        client.logout()
    except Exception:
        pass
