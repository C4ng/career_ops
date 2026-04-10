from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

from app.models import LinkedInConnectionConfig
from app.services.storage.db import SQLiteConfig, connect_sqlite, initialize_schema


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "screening"
    / "detail_fetch.py"
)


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("linkedin_run_detail_fetch_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_detail_fetch_updates_job_details(tmp_path: Path, monkeypatch, capsys) -> None:
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
                easy_apply, stage, stage_reason, stage_updated_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "123",
                "https://www.linkedin.com/jobs/view/123/",
                "AI Engineer",
                "Example",
                "Toronto, ON",
                "remote",
                None,
                1,
                "triaged",
                None,
                "2026-03-27T00:00:00Z",
                "2026-03-27T00:00:00Z",
                "2026-03-27T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(runner_script, "ROOT", tmp_path)
    monkeypatch.setattr(
        runner_script,
        "load_sqlite_config",
        lambda: SQLiteConfig(db_path="data/job_finding.sqlite3"),
    )
    monkeypatch.setattr(
        runner_script,
        "load_linkedin_connection_config",
        lambda: LinkedInConnectionConfig(cdp_url="http://127.0.0.1:9222"),
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
        "fetch_linkedin_job_details",
        lambda cdp_url, candidates: [
            {
                "job_id": candidates[0]["job_id"],
                "linkedin_job_id": candidates[0]["linkedin_job_id"],
                "job_url": candidates[0]["job_url"],
                "apply_link": "https://www.linkedin.com/jobs/view/123/apply/?openSDUIApplyFlow=true",
                "title": candidates[0]["title"],
                "company": candidates[0]["company"],
                "job_description": "Detailed job description",
                "observed_posted_text": "Reposted 2 days ago",
                "work_mode": "hybrid",
                "employment_type": "Full-time",
                "applicant_count_text": "Over 100 people clicked apply",
                "application_status_text": "No longer accepting applications",
                "easy_apply": False,
            }
        ],
    )

    runner_script.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["success"] is True
    assert stdout_payload["status"] == "completed"
    assert stdout_payload["candidate_count"] == 1
    assert stdout_payload["detail_count"] == 1
    assert stdout_payload["db_summary"]["jobs_updated"] == 1
    assert stdout_payload["db_summary"]["descriptions_saved"] == 1
    assert stdout_payload["db_summary"]["apply_link_saved"] == 1
    assert stdout_payload["db_summary"]["employment_type_saved"] == 1
    assert stdout_payload["log_path"].endswith("linkedin_detail_fetch.latest.log")

    verify = sqlite3.connect(db_path)
    try:
        row = verify.execute(
            """
            SELECT job_description, apply_link, observed_posted_text, work_mode, employment_type, applicant_count_text, application_status_text, stage, stage_reason, stage_updated_at
            FROM jobs WHERE linkedin_job_id = ?
            """,
            ("123",),
        ).fetchone()
    finally:
        verify.close()

    assert row[:7] == (
        "Detailed job description",
        "https://www.linkedin.com/jobs/view/123/apply/?openSDUIApplyFlow=true",
        "Reposted 2 days ago",
        "hybrid",
        "Full-time",
        "Over 100 people clicked apply",
        "No longer accepting applications",
    )
    assert row[7] == "not_applicable"
    assert row[8] == "No longer accepting applications"
    assert row[9] is not None
