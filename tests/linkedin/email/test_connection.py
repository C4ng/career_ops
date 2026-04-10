from __future__ import annotations

from app.sources.linkedin.alerts.connection_check import verify_linkedin_email_connection
from app.models import LinkedInEmailConfig


class FakeImapSuccess:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.closed = False
        self.logged_out = False

    def login(self, username: str, password: str):
        return ("OK", [b"logged in"])

    def select(self, mailbox: str):
        return ("OK", [b"12"])

    def close(self) -> None:
        self.closed = True

    def logout(self) -> None:
        self.logged_out = True


class FakeImapLoginFailure:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def login(self, username: str, password: str):
        raise RuntimeError("invalid credentials")

    def close(self) -> None:
        return None

    def logout(self) -> None:
        return None


def _config() -> LinkedInEmailConfig:
    return LinkedInEmailConfig(
        provider="imap",
        host="imap.gmail.com",
        port=993,
        mailbox="INBOX",
        username="person@example.com",
        password_env="LINKEDIN_EMAIL_APP_PASSWORD",
        sender="jobalerts-noreply@linkedin.com",
        lookback_days=7,
        max_messages=30,
    )


def test_verify_linkedin_email_connection_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("LINKEDIN_EMAIL_APP_PASSWORD", "secret")
    monkeypatch.setattr(
        "app.services.email.imaplib.IMAP4_SSL",
        FakeImapSuccess,
    )

    result = verify_linkedin_email_connection(_config())

    assert result.success is True
    assert result.authenticated is True
    assert result.mailbox_selected is True
    assert result.error is None


def test_verify_linkedin_email_connection_fails_when_password_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("LINKEDIN_EMAIL_APP_PASSWORD", raising=False)

    result = verify_linkedin_email_connection(_config())

    assert result.success is False
    assert result.authenticated is False
    assert result.mailbox_selected is False
    assert result.error == "Environment variable LINKEDIN_EMAIL_APP_PASSWORD is not set"


def test_verify_linkedin_email_connection_fails_on_imap_error(monkeypatch) -> None:
    monkeypatch.setenv("LINKEDIN_EMAIL_APP_PASSWORD", "secret")
    monkeypatch.setattr(
        "app.services.email.imaplib.IMAP4_SSL",
        FakeImapLoginFailure,
    )

    result = verify_linkedin_email_connection(_config())

    assert result.success is False
    assert result.authenticated is False
    assert result.mailbox_selected is False
    assert result.error == "invalid credentials"
