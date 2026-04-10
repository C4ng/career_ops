from __future__ import annotations

from app.models import LinkedInJobRankingResult, LinkedInRankingLabeledReason
from app.services.storage.db import connect_sqlite, initialize_schema
from app.services.storage.stages import JobStage
from app.services.storage.ranking import load_enriched_jobs_for_ranking, save_job_rankings


def _insert_job(connection, *, linkedin_job_id: str, stage: str, title: str = "AI Engineer") -> None:
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
            title,
            "Example",
            "Toronto, ON",
            "remote",
            None,
            "Build applied AI systems with Python and LLMs.",
            0,
            stage,
            None,
            None,
            "2026-03-27T00:00:00Z",
            "2026-03-27T00:00:00Z",
        ),
    )


def test_load_enriched_jobs_for_ranking_returns_only_unranked_enriched_jobs(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage=JobStage.ENRICHED)
        _insert_job(connection, linkedin_job_id="456", stage=JobStage.DETAILED)
        _insert_job(connection, linkedin_job_id="789", stage=JobStage.ENRICHED)
        connection.execute(
            """
            INSERT INTO job_rankings (
                job_id, linkedin_job_id, model_name, prompt_version, profile_version,
                role_match_label, role_match_reason,
                level_match_label, level_match_reason,
                preference_match_label, preference_match_reason,
                recommendation, summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                3,
                "789",
                "gemini-2.5-flash",
                "v1",
                "v1",
                "strong",
                "Good role fit",
                "stretch",
                "Some stretch on experience",
                "acceptable",
                "Good preference fit",
                "apply_auto",
                "Already ranked",
                "2026-03-27T00:00:00Z",
            ),
        )
        connection.commit()

        rows = load_enriched_jobs_for_ranking(connection, 10, prompt_version="v1", profile_version="v1")
    finally:
        connection.close()

    assert [row["linkedin_job_id"] for row in rows] == ["123"]


def test_save_job_rankings_inserts_rows(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage=JobStage.ENRICHED)
        connection.commit()

        summary = save_job_rankings(
            connection,
            [
                LinkedInJobRankingResult(
                    linkedin_job_id="123",
                    role_match=LinkedInRankingLabeledReason(label="strong", reason="Strong applied AI scope"),
                    level_match=LinkedInRankingLabeledReason(
                        label="stretch",
                        reason="Acceptable seniority range",
                    ),
                    preference_match=LinkedInRankingLabeledReason(
                        label="preferred",
                        reason="Remote role with acceptable employment terms",
                    ),
                    not_applicable_reason=None,
                    recommendation="apply_auto",
                    summary="Strong fit with slight experience stretch.",
                )
            ],
            model_name="gemini-2.5-flash",
            prompt_version="v1",
            profile_version="v1",
        )
        row = connection.execute(
            """
            SELECT role_match_label, level_match_label, preference_match_label, recommendation, summary
            FROM job_rankings
            WHERE linkedin_job_id = ?
            """,
            ("123",),
        ).fetchone()
        job_row = connection.execute(
            "SELECT stage, stage_reason FROM jobs WHERE linkedin_job_id = ?",
            ("123",),
        ).fetchone()
    finally:
        connection.close()

    assert summary == {
        "rankings_received": 1,
        "rankings_inserted": 1,
        "jobs_missing": 0,
        "jobs_marked_not_applicable": 0,
        "apply_focus_count": 0,
        "apply_auto_count": 1,
        "low_priority_count": 0,
    }
    assert tuple(row) == (
        "strong",
        "stretch",
        "preferred",
        "apply_auto",
        "Strong fit with slight experience stretch.",
    )
    assert tuple(job_row) == (JobStage.RANKED, None)


def test_save_job_rankings_marks_hard_ineligible_job_not_applicable(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage=JobStage.ENRICHED)
        connection.commit()

        summary = save_job_rankings(
            connection,
            [
                LinkedInJobRankingResult(
                    linkedin_job_id="123",
                    role_match=LinkedInRankingLabeledReason(label="strong", reason="Good role alignment"),
                    level_match=LinkedInRankingLabeledReason(label="mismatched", reason="Student-only role"),
                    preference_match=LinkedInRankingLabeledReason(label="preferred", reason="Remote is preferred"),
                    not_applicable_reason="Requires current student enrollment.",
                    recommendation="low_priority",
                    summary="Ineligible because the role requires current student status.",
                )
            ],
            model_name="gemini-2.5-flash",
            prompt_version="v3",
            profile_version="v1",
        )
        row = connection.execute(
            "SELECT stage, stage_reason FROM jobs WHERE linkedin_job_id = ?",
            ("123",),
        ).fetchone()
    finally:
        connection.close()

    assert summary["jobs_marked_not_applicable"] == 1
    assert tuple(row) == ("not_applicable", "Requires current student enrollment.")
