from __future__ import annotations

import json

from app.services.storage.db import connect_sqlite, initialize_schema
from app.services.storage.enrichment import load_detailed_jobs_for_enrichment, save_job_enrichments


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


def test_load_detailed_jobs_for_enrichment_returns_only_detailed_jobs(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage="detailed", job_description="Detailed description")
        _insert_job(connection, linkedin_job_id="456", stage="triaged", job_description="Should not load")
        _insert_job(connection, linkedin_job_id="789", stage="enriched", job_description="Already enriched")
        connection.commit()

        rows = load_detailed_jobs_for_enrichment(connection, 10)
    finally:
        connection.close()

    assert rows == [
        {
            "job_id": 1,
            "linkedin_job_id": "123",
            "job_url": "https://www.linkedin.com/jobs/view/123/",
            "apply_link": None,
            "title": "Title 123",
            "company": "Example",
            "location_text": "Toronto, ON",
            "work_mode": "remote",
            "observed_posted_text": None,
            "employment_type": None,
            "applicant_count_text": None,
            "application_status_text": None,
            "easy_apply": False,
            "job_description": "Detailed description",
        }
    ]


def test_save_job_enrichments_updates_jobs_table(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage="detailed", job_description="Detailed description")
        connection.commit()

        summary = save_job_enrichments(
            connection,
            [
                {
                    "linkedin_job_id": "123",
                    "work_mode": "hybrid",
                    "salary_text": "$140,000-$170,000 CAD",
                    "employment_type": "Full-time",
                    "company_intro": ["AI company serving enterprise customers"],
                    "role_scope": ["Build applied AI systems", "Ship product features"],
                    "requirements": {
                        "summary": ["Applied AI role"],
                        "skills": ["Python", "LLMs"],
                        "experience": ["Production ML experience"],
                        "tech": ["PyTorch"],
                        "education": [],
                        "constraints": ["Hybrid in Toronto"],
                        "other": [],
                    },
                    "benefits": ["Flexible work"],
                    "application_details": ["Applications reviewed on a rolling basis"],
                }
            ],
        )
        row = connection.execute(
            """
            SELECT work_mode, salary_text, employment_type, company_intro, role_scope, requirements, benefits, application_details, stage, stage_reason, stage_updated_at
            FROM jobs WHERE linkedin_job_id = ?
            """,
            ("123",),
        ).fetchone()
    finally:
        connection.close()

    assert summary == {
        "enrichments_received": 1,
        "jobs_updated": 1,
        "jobs_missing": 0,
        "work_mode_saved": 1,
        "salary_text_saved": 1,
        "employment_type_saved": 1,
        "company_intro_saved": 1,
        "role_scope_saved": 1,
        "requirements_saved": 1,
        "benefits_saved": 1,
        "application_details_saved": 1,
    }
    assert row[0] == "hybrid"
    assert row[1] == "$140,000-$170,000 CAD"
    assert row[2] == "Full-time"
    assert json.loads(row[3]) == ["AI company serving enterprise customers"]
    assert json.loads(row[4]) == ["Build applied AI systems", "Ship product features"]
    assert json.loads(row[5])["skills"] == ["Python", "LLMs"]
    assert json.loads(row[6]) == ["Flexible work"]
    assert json.loads(row[7]) == ["Applications reviewed on a rolling basis"]
    assert row[8] == "enriched"
    assert row[9] is None
    assert row[10] is not None
