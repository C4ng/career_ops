from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.models import LinkedInJobCard
from app.services.storage.db import connect_sqlite, initialize_schema
from app.services.storage.jobs import persist_linkedin_job_cards


def _job_card(
    *,
    linkedin_job_id: str = "123",
    source_type: str = "keyword_search",
    observed_at: datetime | None = datetime(2026, 3, 27, 12, 0, tzinfo=UTC),
    title: str = "AI Engineer",
    company: str = "Example",
    location_text: str | None = "Toronto, ON",
    job_description: str | None = None,
    employment_type: str | None = None,
    applicant_count_text: str | None = None,
    application_status_text: str | None = None,
) -> LinkedInJobCard:
    return LinkedInJobCard(
        source_type=source_type,
        observed_at=observed_at,
        linkedin_job_id=linkedin_job_id,
        job_url=f"https://www.linkedin.com/jobs/view/{linkedin_job_id}/",
        apply_link=None,
        title=title,
        company=company,
        location_text=location_text,
        work_mode="remote",
        observed_posted_text="2 days ago",
        salary_text="$100K/yr",
        job_description=job_description,
        employment_type=employment_type,
        applicant_count_text=applicant_count_text,
        application_status_text=application_status_text,
        easy_apply=True,
        badges=["Easy Apply"],
    )


def test_persist_linkedin_job_cards_inserts_job_and_observation(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        summary = persist_linkedin_job_cards(connection, [_job_card()])

        job_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        observation_count = connection.execute("SELECT COUNT(*) FROM job_observations").fetchone()[0]
        job_row = connection.execute(
            "SELECT linkedin_job_id, title, company, easy_apply, job_description, apply_link FROM jobs"
        ).fetchone()
    finally:
        connection.close()

    assert summary["jobs_inserted"] == 1
    assert summary["jobs_updated"] == 0
    assert summary["observations_inserted"] == 1
    assert job_count == 1
    assert observation_count == 1
    assert tuple(job_row) == ("123", "AI Engineer", "Example", 1, None, None)


def test_persist_linkedin_job_cards_updates_existing_job_and_skips_duplicate_observation(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        first = _job_card(location_text="Toronto, ON")
        second = _job_card(
            observed_at=datetime(2026, 3, 27, 13, 0, tzinfo=UTC),
            job_description="Detailed description",
            employment_type="Full-time",
            applicant_count_text="Over 100 applicants",
            application_status_text="No longer accepting applications",
        )
        second.apply_link = "https://www.linkedin.com/jobs/view/123/apply/?openSDUIApplyFlow=true"
        second.observed_posted_text = "Reposted 2 days ago"
        summary_first = persist_linkedin_job_cards(connection, [first])
        summary_second = persist_linkedin_job_cards(connection, [second])

        job_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        observation_count = connection.execute("SELECT COUNT(*) FROM job_observations").fetchone()[0]
        job_row = connection.execute(
            """
            SELECT job_description, apply_link, observed_posted_text, employment_type, applicant_count_text, application_status_text
            FROM jobs
            WHERE linkedin_job_id = ?
            """,
            ("123",),
        ).fetchone()
    finally:
        connection.close()

    assert summary_first["jobs_inserted"] == 1
    assert summary_second["jobs_updated"] == 1
    assert summary_second["observations_skipped"] == 0
    assert job_count == 1
    assert observation_count == 2
    assert tuple(job_row) == (
        "Detailed description",
        "https://www.linkedin.com/jobs/view/123/apply/?openSDUIApplyFlow=true",
        "Reposted 2 days ago",
        "Full-time",
        "Over 100 applicants",
        "No longer accepting applications",
    )


def test_persist_linkedin_job_cards_skips_cards_missing_required_fields(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        invalid = LinkedInJobCard(
            source_type="email_notifications",
            linkedin_job_id="123",
            job_url="https://www.linkedin.com/jobs/view/123/",
            title=None,
            company="Example",
        )
        summary = persist_linkedin_job_cards(connection, [invalid])
    finally:
        connection.close()

    assert summary["cards_skipped"] == 1
    assert summary["skip_reasons"] == {"missing_required_fields:title": 1}
