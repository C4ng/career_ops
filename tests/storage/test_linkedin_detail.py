from __future__ import annotations

from pathlib import Path

from app.services.storage.db import connect_sqlite, initialize_schema
from app.services.storage.job_details import load_triaged_jobs_for_detail_fetch, save_job_details


def _insert_job(
    connection,
    *,
    linkedin_job_id: str,
    stage: str,
    job_description: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO jobs (
            linkedin_job_id, job_url, title, company, location_text, work_mode, salary_text,
            job_description, easy_apply, stage, stage_reason, stage_updated_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            linkedin_job_id,
            f"https://www.linkedin.com/jobs/view/{linkedin_job_id}/",
            f"Title {linkedin_job_id}",
            "Example",
            "Toronto, ON",
            "remote",
            None,
            job_description,
            0,
            stage,
            None,
            None,
            "2026-03-27T00:00:00Z",
            "2026-03-27T00:00:00Z",
        ),
    )


def test_load_triaged_jobs_for_detail_fetch_returns_only_triaged_jobs(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage="triaged")
        _insert_job(connection, linkedin_job_id="456", stage="not_applicable")
        _insert_job(
            connection,
            linkedin_job_id="789",
            stage="detailed",
            job_description="Existing description",
        )
        connection.commit()

        rows = load_triaged_jobs_for_detail_fetch(connection)
    finally:
        connection.close()

    assert rows == [
        {
            "job_id": 1,
            "linkedin_job_id": "123",
            "job_url": "https://www.linkedin.com/jobs/view/123/",
            "title": "Title 123",
            "company": "Example",
            "location_text": "Toronto, ON",
            "work_mode": "remote",
        },
    ]


def test_save_job_details_updates_jobs_table(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage="triaged")
        connection.commit()

        summary = save_job_details(
            connection,
            [
                {
                    "linkedin_job_id": "123",
                    "job_description": "Detailed job description",
                    "apply_link": "https://example.com/apply",
                    "observed_posted_text": "Reposted 2 days ago",
                    "work_mode": "hybrid",
                    "employment_type": "Full-time",
                    "applicant_count_text": "Over 100 people clicked apply",
                    "application_status_text": "No longer accepting applications",
                    "easy_apply": False,
                }
            ],
        )
        row = connection.execute(
            """
            SELECT job_description, apply_link, observed_posted_text, work_mode, employment_type, applicant_count_text, application_status_text, stage, stage_reason, stage_updated_at
            FROM jobs WHERE linkedin_job_id = ?
            """,
            ("123",),
        ).fetchone()
    finally:
        connection.close()

    assert summary == {
        "details_received": 1,
        "jobs_updated": 1,
        "jobs_missing": 0,
        "descriptions_saved": 1,
        "descriptions_missing": 0,
        "apply_link_saved": 1,
        "posted_text_saved": 1,
        "work_mode_saved": 1,
        "employment_type_saved": 1,
        "applicant_count_saved": 1,
        "application_status_saved": 1,
    }
    assert row[:7] == (
        "Detailed job description",
        "https://example.com/apply",
        "Reposted 2 days ago",
        "hybrid",
        "Full-time",
        "Over 100 people clicked apply",
        "No longer accepting applications",
    )
    assert row[7] == "not_applicable"
    assert row[8] == "No longer accepting applications"
    assert row[9] is not None
