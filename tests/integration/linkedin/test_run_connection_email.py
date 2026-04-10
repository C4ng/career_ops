from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.models import (
    LinkedInEmailConfig,
    LinkedInEmailConnectionResult,
)


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "connection"
    / "email.py"
)


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("linkedin_run_connection_email_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_connection_email_prints_connection_status(
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
        password_env="LINKEDIN_EMAIL_APP_PASSWORD",
        sender="jobalerts-noreply@linkedin.com",
        lookback_days=7,
        max_messages=30,
    )
    result = LinkedInEmailConnectionResult(
        success=True,
        provider="imap",
        host="imap.gmail.com",
        port=993,
        mailbox="INBOX",
        username="person@example.com",
        sender="jobalerts-noreply@linkedin.com",
        lookback_days=7,
        max_messages=30,
        authenticated=True,
        mailbox_selected=True,
    )

    logs_path = tmp_path / "data" / "logs"
    monkeypatch.setattr(runner_script, "load_linkedin_email_connection_config", lambda: config)
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
        "verify_linkedin_email_connection",
        lambda loaded_config: result,
    )

    runner_script.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["success"] is True
    assert stdout_payload["provider"] == "imap"
    assert stdout_payload["host"] == "imap.gmail.com"
    assert stdout_payload["port"] == 993
    assert stdout_payload["mailbox"] == "INBOX"
    assert stdout_payload["username"] == "person@example.com"
    assert stdout_payload["authenticated"] is True
    assert stdout_payload["mailbox_selected"] is True
    assert stdout_payload["error"] is None
    assert stdout_payload["log_path"].endswith("linkedin_email_connection.latest.log")
