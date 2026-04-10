from __future__ import annotations

from app.models import LinkedInTitleTriageDecision
from app.services.storage.db import connect_sqlite, initialize_schema
from app.services.storage.title_triage import load_discovered_jobs, save_title_triage_results


def _seed_jobs(connection) -> None:
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
            "AI Engineer",
            "Example",
            "Toronto, ON",
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
            easy_apply, stage, stage_reason, stage_updated_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "456",
            "https://www.linkedin.com/jobs/view/456/",
            "Backend Engineer",
            "Other",
            "Vancouver, BC",
            "hybrid",
            None,
            0,
            "not_applicable",
            "No AI cue",
            "2026-03-27T00:00:00Z",
            "2026-03-27T00:00:00Z",
            "2026-03-27T00:00:00Z",
        ),
    )
    connection.commit()


def test_load_discovered_jobs_returns_only_discovered_jobs(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _seed_jobs(connection)
        candidates = load_discovered_jobs(connection, 10)
    finally:
        connection.close()

    assert len(candidates) == 1
    assert candidates[0].linkedin_job_id == "123"
    assert candidates[0].title == "AI Engineer"


def test_save_title_triage_results_updates_jobs_table(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _seed_jobs(connection)
        summary = save_title_triage_results(
            connection,
            [
                LinkedInTitleTriageDecision(
                    linkedin_job_id="123",
                    decision="keep",
                    reason="Explicit AI title and remote is acceptable.",
                )
            ],
            model_name="gpt-5-mini",
        )
        row = connection.execute(
            """
            SELECT stage, stage_reason, title_triage_model
            FROM jobs WHERE linkedin_job_id = '123'
            """
        ).fetchone()
    finally:
        connection.close()

    assert summary["jobs_updated"] == 1
    assert summary["keep_count"] == 1
    assert tuple(row) == (
        "triaged",
        None,
        "gpt-5-mini",
    )
