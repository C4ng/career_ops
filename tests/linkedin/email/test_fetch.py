from __future__ import annotations

from app.sources.linkedin.alerts.fetch import (
    fetch_linkedin_application_confirmation_emails,
    fetch_linkedin_job_alert_emails,
)
from app.models import LinkedInEmailConfig


RAW_EMAIL_ONE = (
    b"Message-ID: <message-1@example.com>\r\n"
    b"From: jobalerts-noreply@linkedin.com\r\n"
    b"Subject: LinkedIn Job Alerts\r\n"
    b"Date: Thu, 26 Mar 2026 15:10:00 -0400\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: multipart/alternative; boundary=\"sep\"\r\n"
    b"\r\n"
    b"--sep\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"AI Research Intern - 8 months\r\n"
    b"TD\r\n"
    b"Toronto, ON\r\n"
    b"Apply with resume & profile\r\n"
    b"View job: https://www.linkedin.com/comm/jobs/view/4390302068/?trackingId=abc\r\n"
    b"--sep\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n"
    b"\r\n"
    b"<html><body><p>HTML body one</p></body></html>\r\n"
    b"--sep--\r\n"
)

RAW_EMAIL_TWO = (
    b"Message-ID: <message-2@example.com>\r\n"
    b"From: jobalerts-noreply@linkedin.com\r\n"
    b"Subject: Dynamic LinkedIn Job Subject\r\n"
    b"Date: Thu, 26 Mar 2026 16:10:00 -0400\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Research Engineer\r\n"
    b"RBC\r\n"
    b"Toronto, ON\r\n"
    b"Fast growing\r\n"
    b"View job: https://www.linkedin.com/comm/jobs/view/4326363841/?trackingId=def\r\n"
)

RAW_EMAIL_THREE = (
    b"Message-ID: <message-3@example.com>\r\n"
    b"From: LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>\r\n"
    b"Subject: Dynamic LinkedIn Job Subject\r\n"
    b"Date: Thu, 26 Mar 2026 17:10:00 -0400\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Your job alert for AI in Toronto\r\n"
    b"New jobs match your preferences.\r\n"
    b"AI software engineer - Toronto\r\n"
    b"View job: https://www.linkedin.com/comm/jobs/view/1111111111/?trackingId=ignore\r\n"
    b"Machine Learning Engineer (AI Agents)\r\n"
    b"Cresta\r\n"
    b"Canada (Remote)\r\n"
    b"Easy Apply\r\n"
    b"View job: https://www.linkedin.com/comm/jobs/view/2222222222/?trackingId=keep\r\n"
    b"Senior AI Engineer\r\n"
    b"Example Corp\r\n"
    b"Toronto, ON\r\n"
    b"View job: https://www.linkedin.com/comm/jobs/view/3333333333/?trackingId=filtered\r\n"
)

RAW_CONFIRMATION_ONE = (
    b"Message-ID: <confirmation-1@example.com>\r\n"
    b"From: jobs-noreply@linkedin.com\r\n"
    b"Subject: Your application was sent to Compunnel Inc.\r\n"
    b"Date: Mon, 30 Mar 2026 17:02:00 -0400\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Your application was sent to Compunnel Inc.\r\n"
    b"Job title: GenAI Developer -- DWIDC5657517\r\n"
    b"View job: https://www.linkedin.com/comm/jobs/view/4390646108/?trackingId=abc\r\n"
)

class FakeImapFetchSuccess:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.selected_mailbox = None
        self.search_charset = None
        self.search_criteria = None

    def login(self, username: str, password: str):
        return ("OK", [b"logged in"])

    def select(self, mailbox: str):
        self.selected_mailbox = mailbox
        return ("OK", [b"2"])

    def search(self, charset, *criteria):
        self.search_charset = charset
        self.search_criteria = criteria
        return ("OK", [b"1 2 3"])

    def fetch(self, sequence_id: str, message_parts: str):
        if sequence_id == "3":
            payload = RAW_EMAIL_ONE
        elif sequence_id == "2":
            payload = RAW_EMAIL_THREE
        else:
            payload = RAW_EMAIL_TWO
        return ("OK", [(b"RFC822", payload)])

    def close(self) -> None:
        return None

    def logout(self) -> None:
        return None


def _config(max_messages: int = 30) -> LinkedInEmailConfig:
    return LinkedInEmailConfig(
        provider="imap",
        host="imap.gmail.com",
        port=993,
        mailbox="INBOX",
        username="person@example.com",
        password_env="GMAIL_PASSWORD",
        sender="jobalerts-noreply@linkedin.com",
        lookback_days=1,
        max_messages=max_messages,
        title_exclude_contains=["senior", "staff", "manager", "lead"],
    )


def _confirmation_config(max_messages: int = 30) -> LinkedInEmailConfig:
    return LinkedInEmailConfig(
        provider="imap",
        host="imap.gmail.com",
        port=993,
        mailbox="INBOX",
        username="person@example.com",
        password_env="GMAIL_PASSWORD",
        sender="jobs-noreply@linkedin.com",
        lookback_days=1,
        max_messages=max_messages,
        title_exclude_contains=[],
    )


def test_fetch_linkedin_job_alert_emails_returns_matched_messages(monkeypatch) -> None:
    monkeypatch.setenv("GMAIL_PASSWORD", "secret")
    fake_client_holder: dict[str, FakeImapFetchSuccess] = {}

    def factory(host: str, port: int) -> FakeImapFetchSuccess:
        client = FakeImapFetchSuccess(host, port)
        fake_client_holder["client"] = client
        return client

    monkeypatch.setattr(
        "app.services.email.imaplib.IMAP4_SSL",
        factory,
    )

    result = fetch_linkedin_job_alert_emails(_config())

    assert result.success is True
    assert result.authenticated is True
    assert result.mailbox_selected is True
    assert result.matched_message_count == 3
    assert len(result.messages) == 3
    assert len(result.job_cards) == 3
    assert result.job_cards[0].source_type == "email_notifications"
    assert result.job_cards[0].linkedin_job_id == "4390302068"
    assert result.job_cards[0].job_url == "https://www.linkedin.com/jobs/view/4390302068/"
    assert result.job_cards[0].title == "AI Research Intern - 8 months"
    assert result.job_cards[0].company == "TD"
    assert result.job_cards[0].location_text == "Toronto, ON"
    assert result.messages[0].sequence_id == "3"
    assert result.messages[0].message_id == "<message-1@example.com>"
    assert result.messages[0].html_body == "<html><body><p>HTML body one</p></body></html>"
    assert result.messages[1].sequence_id == "2"
    assert "Machine Learning Engineer (AI Agents)" in result.messages[1].text_body
    assert result.messages[2].sequence_id == "1"
    assert "Research Engineer" in result.messages[2].text_body
    assert [job_card.title for job_card in result.job_cards] == [
        "AI Research Intern - 8 months",
        "Machine Learning Engineer (AI Agents)",
        "Research Engineer",
    ]
    assert [job_card.linkedin_job_id for job_card in result.job_cards] == [
        "4390302068",
        "2222222222",
        "4326363841",
    ]
    assert fake_client_holder["client"].search_charset is None
    assert fake_client_holder["client"].search_criteria[:2] == (
        "FROM",
        '"jobalerts-noreply@linkedin.com"',
    )
    assert fake_client_holder["client"].search_criteria[2] == "SINCE"
    assert isinstance(fake_client_holder["client"].search_criteria[3], str)
    assert fake_client_holder["client"].search_criteria[3]


def test_fetch_linkedin_job_alert_emails_applies_max_messages_limit(monkeypatch) -> None:
    monkeypatch.setenv("GMAIL_PASSWORD", "secret")
    monkeypatch.setattr(
        "app.services.email.imaplib.IMAP4_SSL",
        FakeImapFetchSuccess,
    )

    result = fetch_linkedin_job_alert_emails(_config(max_messages=1))

    assert result.matched_message_count == 3
    assert len(result.job_cards) == 1
    assert result.job_cards[0].linkedin_job_id == "4390302068"
    assert [message.sequence_id for message in result.messages] == ["3"]


class FakeImapConfirmationSuccess:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def login(self, username: str, password: str):
        return ("OK", [b"logged in"])

    def select(self, mailbox: str):
        return ("OK", [b"1"])

    def search(self, charset, *criteria):
        return ("OK", [b"1"])

    def fetch(self, sequence_id: str, message_parts: str):
        return ("OK", [(b"RFC822", RAW_CONFIRMATION_ONE)])

    def close(self) -> None:
        return None

    def logout(self) -> None:
        return None


def test_fetch_linkedin_application_confirmation_emails_extracts_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("GMAIL_PASSWORD", "secret")
    monkeypatch.setattr(
        "app.services.email.imaplib.IMAP4_SSL",
        FakeImapConfirmationSuccess,
    )

    result = fetch_linkedin_application_confirmation_emails(_confirmation_config())

    assert result.success is True
    assert result.matched_message_count == 1
    assert len(result.messages) == 1
    assert len(result.confirmations) == 1
    confirmation = result.confirmations[0]
    assert confirmation.message_id == "<confirmation-1@example.com>"
    assert confirmation.linkedin_job_id == "4390646108"
    assert confirmation.job_url == "https://www.linkedin.com/jobs/view/4390646108/"
    assert confirmation.company == "Compunnel Inc"
    assert confirmation.title == "GenAI Developer -- DWIDC5657517"
    assert confirmation.subject == "Your application was sent to Compunnel Inc."
