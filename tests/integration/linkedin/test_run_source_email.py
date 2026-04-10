from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

from app.models import LinkedInEmailConfig, LinkedInEmailFetchResult, LinkedInJobCard
from app.services.storage.db import SQLiteConfig


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "source"
    / "email.py"
)


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("linkedin_run_source_email_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_source_email_prints_fetch_status(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runner_script = _load_runner_module()
    config = LinkedInEmailConfig(
        provider="imap",
        host="imap.gmail.com",
        port=993,
        mailbox="INBOX",
        username="person@example.com",
        password_env="GMAIL_PASSWORD",
        sender="jobalerts-noreply@linkedin.com",
        lookback_days=1,
        max_messages=30,
        title_exclude_contains=["senior", "staff"],
    )
    result = LinkedInEmailFetchResult(
        success=True,
        provider="imap",
        host="imap.gmail.com",
        port=993,
        mailbox="INBOX",
        username="person@example.com",
        sender="jobalerts-noreply@linkedin.com",
        lookback_days=1,
        max_messages=30,
        authenticated=True,
        mailbox_selected=True,
        matched_message_count=4,
        job_cards=[
            LinkedInJobCard(
                source_type="email_notifications",
                linkedin_job_id="123",
                job_url="https://www.linkedin.com/jobs/view/123/",
                title="AI Engineer",
                company="Example",
                raw_card_text="raw snippet",
            )
        ],
    )

    logs_path = tmp_path / "data" / "logs"
    db_path = tmp_path / "data" / "job_finding.sqlite3"

    monkeypatch.setattr(runner_script, "ROOT", tmp_path)
    monkeypatch.setattr(runner_script, "load_linkedin_email_connection_config", lambda: config)
    monkeypatch.setattr(runner_script, "load_sqlite_config", lambda: SQLiteConfig(db_path="data/job_finding.sqlite3"))
    monkeypatch.setattr(
        runner_script,
        "setup_logging",
        lambda name: {
            "latest": logs_path / f"{name}.latest.log",
            "history": logs_path / f"{name}.history.log",
        },
    )
    monkeypatch.setattr(
        runner_script,
        "fetch_linkedin_job_alert_emails",
        lambda loaded_config: result,
    )

    runner_script.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["success"] is True
    assert stdout_payload["provider"] == "imap"
    assert stdout_payload["host"] == "imap.gmail.com"
    assert stdout_payload["mailbox"] == "INBOX"
    assert stdout_payload["username"] == "person@example.com"
    assert stdout_payload["sender"] == "jobalerts-noreply@linkedin.com"
    assert stdout_payload["matched_message_count"] == 4
    assert stdout_payload["job_card_count"] == 1
    assert stdout_payload["error"] is None
    assert stdout_payload["db_path"] == str(db_path)
    assert stdout_payload["db_summary"]["cards_read"] == 1
    assert stdout_payload["db_summary"]["jobs_inserted"] == 1
    assert stdout_payload["db_summary"]["observations_inserted"] == 1
    assert stdout_payload["log_path"].endswith("linkedin_email_source.latest.log")

    connection = sqlite3.connect(db_path)
    try:
        job_row = connection.execute(
            "SELECT linkedin_job_id, title, company FROM jobs"
        ).fetchone()
        observation_count = connection.execute("SELECT COUNT(*) FROM job_observations").fetchone()[0]
    finally:
        connection.close()

    assert job_row == ("123", "AI Engineer", "Example")
    assert observation_count == 1
