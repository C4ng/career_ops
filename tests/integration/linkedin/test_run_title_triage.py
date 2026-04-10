from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

from app.models import (
    LinkedInTitleTriageDecision,
    LinkedInTitleTriageConfig,
)
from app.services.llm.config import TitleTriageLLMConfig
from app.services.storage.db import SQLiteConfig, connect_sqlite, initialize_schema


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "screening"
    / "title_triage.py"
)


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("linkedin_run_title_triage_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_title_triage_updates_job_rows(tmp_path: Path, monkeypatch, capsys) -> None:
    runner_script = _load_runner_module()
    db_path = tmp_path / "data" / "job_finding.sqlite3"
    logs_path = tmp_path / "data" / "logs"

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        connection.execute(
            """
            INSERT INTO jobs (
                linkedin_job_id, job_url, title, company, location_text, work_mode, salary_text,
                easy_apply, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "123",
                "https://www.linkedin.com/jobs/view/123/",
                "LLM Engineer",
                "Example",
                "Canada (Remote)",
                "remote",
                None,
                1,
                "2026-03-27T00:00:00Z",
                "2026-03-27T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO jobs (
                linkedin_job_id, job_url, title, company, location_text, work_mode, salary_text,
                easy_apply, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "456",
                "https://www.linkedin.com/jobs/view/456/",
                "AI Research Engineer",
                "Example Two",
                "Toronto, ON",
                "hybrid",
                None,
                0,
                "2026-03-27T00:00:00Z",
                "2026-03-27T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(runner_script, "ROOT", tmp_path)
    monkeypatch.setattr(runner_script, "load_sqlite_config", lambda: SQLiteConfig(db_path="data/job_finding.sqlite3"))
    monkeypatch.setattr(
        runner_script,
        "load_title_triage_llm_config",
        lambda: TitleTriageLLMConfig(model="gpt-5-mini", batch_size=1),
    )
    monkeypatch.setattr(
        runner_script,
        "load_linkedin_title_triage_config",
        lambda: LinkedInTitleTriageConfig(
            goal="Triage LinkedIn titles",
            wanted_roles=["Machine Learning Engineer"],
            wanted_technical_cues=["llm"],
            decision_rules=["Prefer keep when uncertain."],
            location_policy=["Remote is acceptable anywhere."],
        ),
    )
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
        "triage_linkedin_job_titles",
        lambda llm_config, triage_config, candidates: [
            LinkedInTitleTriageDecision(
                linkedin_job_id=candidates[0].linkedin_job_id,
                decision="keep",
                reason=f"{candidates[0].title} is acceptable.",
            )
        ],
    )

    runner_script.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["success"] is True
    assert stdout_payload["status"] == "completed"
    assert stdout_payload["candidate_count"] == 2
    assert stdout_payload["decision_count"] == 2
    assert stdout_payload["batch_count"] == 2
    assert stdout_payload["db_summary"]["jobs_updated"] == 2

    verify = sqlite3.connect(db_path)
    try:
        rows = verify.execute(
            """
            SELECT linkedin_job_id, stage, stage_reason, title_triage_model
            FROM jobs
            ORDER BY linkedin_job_id
            """
        ).fetchall()
    finally:
        verify.close()

    assert rows == [
        ("123", "triaged", None, "gpt-5-mini"),
        ("456", "triaged", None, "gpt-5-mini"),
    ]
