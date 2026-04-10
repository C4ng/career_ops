"""Happy-path tests for complex storage functions (Issue #16)."""
from __future__ import annotations

import pytest

from app.models import LinkedInJobRankingResult, LinkedInRankingLabeledReason
from app.services.storage.applications import (
    create_job_application,
    get_or_create_job_application,
    load_application_questions,
    load_job_application,
    mark_job_as_applied_from_confirmation,
    replace_application_questions,
    update_job_application_status,
)
from app.services.storage.db import connect_sqlite, initialize_schema
from app.services.storage.job_details import save_job_details
from app.services.storage.enrichment import save_job_enrichments
from app.services.storage.ranking import save_job_rankings
from app.services.storage.stages import JobStage
from app.models import LinkedInApplicationAnswerProposal, LinkedInApplicationQuestion


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_connection(tmp_path):
    connection = connect_sqlite(tmp_path / "test.sqlite3")
    initialize_schema(connection)
    return connection


def _seed_job(connection, linkedin_job_id: str, stage: str = JobStage.DISCOVERED) -> int:
    cursor = connection.execute(
        """
        INSERT INTO jobs (linkedin_job_id, job_url, title, company, easy_apply,
                          stage, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'now', 'now')
        """,
        (linkedin_job_id, f"https://li.com/jobs/{linkedin_job_id}/", "AI Engineer", "Acme", 1, stage),
    )
    connection.commit()
    return int(cursor.lastrowid)


# ---------------------------------------------------------------------------
# save_job_details
# ---------------------------------------------------------------------------


def test_save_job_details_advances_stage_to_detailed(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        job_id = _seed_job(connection, "j1", stage=JobStage.TRIAGED)
        result = save_job_details(
            connection,
            [
                {
                    "linkedin_job_id": "j1",
                    "job_description": "Great job doing ML stuff.",
                    "apply_link": "https://apply.example.com/",
                    "easy_apply": True,
                }
            ],
        )
        row = connection.execute("SELECT stage, job_description FROM jobs WHERE linkedin_job_id='j1'").fetchone()
    finally:
        connection.close()

    assert result["jobs_updated"] == 1
    assert result["descriptions_saved"] == 1
    assert row["stage"] == JobStage.DETAILED
    assert row["job_description"] == "Great job doing ML stuff."


def test_save_job_details_marks_not_applicable_when_closed(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        _seed_job(connection, "j1", stage=JobStage.TRIAGED)
        save_job_details(
            connection,
            [{"linkedin_job_id": "j1", "application_status_text": "No longer accepting applications"}],
        )
        row = connection.execute("SELECT stage, stage_reason FROM jobs WHERE linkedin_job_id='j1'").fetchone()
    finally:
        connection.close()

    assert row["stage"] == JobStage.NOT_APPLICABLE
    assert "No longer accepting applications" in row["stage_reason"]


def test_save_job_details_rejects_wrong_source_stage(tmp_path) -> None:
    from app.services.storage.stages import InvalidStageTransitionError

    connection = _make_connection(tmp_path)
    try:
        _seed_job(connection, "j1", stage=JobStage.DISCOVERED)  # not TRIAGED
        with pytest.raises(InvalidStageTransitionError):
            save_job_details(connection, [{"linkedin_job_id": "j1", "job_description": "x"}])
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# save_job_enrichments
# ---------------------------------------------------------------------------


def test_save_job_enrichments_advances_stage_to_enriched(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        _seed_job(connection, "j1", stage=JobStage.DETAILED)
        result = save_job_enrichments(
            connection,
            [
                {
                    "linkedin_job_id": "j1",
                    "company_intro": ["Acme builds the future"],
                    "requirements": {"skills": ["Python"], "summary": [], "experience": [],
                                     "tech": [], "education": [], "constraints": [], "other": []},
                }
            ],
        )
        row = connection.execute("SELECT stage FROM jobs WHERE linkedin_job_id='j1'").fetchone()
    finally:
        connection.close()

    assert result["jobs_updated"] == 1
    assert row["stage"] == JobStage.ENRICHED


# ---------------------------------------------------------------------------
# save_job_rankings
# ---------------------------------------------------------------------------


def _make_ranking(linkedin_job_id: str, *, not_applicable: bool = False) -> LinkedInJobRankingResult:
    lr = LinkedInRankingLabeledReason
    return LinkedInJobRankingResult(
        linkedin_job_id=linkedin_job_id,
        role_match=lr(label="strong", reason="Good title match"),
        level_match=lr(label="appropriate", reason="Appropriate seniority"),
        preference_match=lr(label="preferred", reason="Remote ok"),
        not_applicable_reason="Too senior" if not_applicable else None,
        recommendation="apply_focus",
        summary="Top pick.",
    )


def test_save_job_rankings_inserts_ranking_row(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        _seed_job(connection, "j1", stage=JobStage.ENRICHED)
        result = save_job_rankings(
            connection,
            [_make_ranking("j1")],
            model_name="gemini-2.5-flash",
            prompt_version="v1",
            profile_version="v1",
        )
        ranking_row = connection.execute(
            "SELECT recommendation FROM job_rankings WHERE linkedin_job_id='j1'"
        ).fetchone()
        job_row = connection.execute("SELECT stage FROM jobs WHERE linkedin_job_id='j1'").fetchone()
    finally:
        connection.close()

    assert result["rankings_inserted"] == 1
    assert result["apply_focus_count"] == 1
    assert ranking_row["recommendation"] == "apply_focus"
    assert job_row["stage"] == JobStage.RANKED


def test_save_job_rankings_marks_not_applicable(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        _seed_job(connection, "j1", stage=JobStage.ENRICHED)
        result = save_job_rankings(
            connection,
            [_make_ranking("j1", not_applicable=True)],
            model_name="gemini-2.5-flash",
            prompt_version="v1",
            profile_version="v1",
        )
        row = connection.execute("SELECT stage, stage_reason FROM jobs WHERE linkedin_job_id='j1'").fetchone()
    finally:
        connection.close()

    assert result["jobs_marked_not_applicable"] == 1
    assert row["stage"] == JobStage.NOT_APPLICABLE
    assert "Too senior" in row["stage_reason"]


# ---------------------------------------------------------------------------
# create_job_application / get_or_create / update / load
# ---------------------------------------------------------------------------


def test_create_and_load_job_application(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        job_id = _seed_job(connection, "j1", stage=JobStage.RANKED)
        app_id = create_job_application(
            connection,
            job_id=job_id,
            linkedin_job_id="j1",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v1",
            ranking_profile_version="v1",
            recommendation="apply_focus",
        )
        row = load_job_application(connection, app_id)
    finally:
        connection.close()

    assert row is not None
    assert row["application_id"] == app_id
    assert row["status"] == "opened"
    assert row["linkedin_job_id"] == "j1"


def test_get_or_create_returns_existing_application(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        job_id = _seed_job(connection, "j1", stage=JobStage.RANKED)
        app_id_1, created_1 = get_or_create_job_application(
            connection,
            job_id=job_id,
            linkedin_job_id="j1",
            application_type="linkedin_easy_apply",
        )
        app_id_2, created_2 = get_or_create_job_application(
            connection,
            job_id=job_id,
            linkedin_job_id="j1",
            application_type="linkedin_easy_apply",
        )
    finally:
        connection.close()

    assert created_1 is True
    assert created_2 is False
    assert app_id_1 == app_id_2


def test_update_job_application_status(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        job_id = _seed_job(connection, "j1", stage=JobStage.RANKED)
        app_id = create_job_application(
            connection,
            job_id=job_id,
            linkedin_job_id="j1",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v1",
            ranking_profile_version="v1",
            recommendation="apply_focus",
        )
        update_job_application_status(
            connection,
            app_id,
            status="in_progress",
            last_seen_url="https://li.com/jobs/j1/",
        )
        row = load_job_application(connection, app_id)
    finally:
        connection.close()

    assert row["status"] == "in_progress"
    assert row["last_seen_url"] == "https://li.com/jobs/j1/"


def test_replace_and_load_application_questions(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        job_id = _seed_job(connection, "j1", stage=JobStage.RANKED)
        app_id = create_job_application(
            connection,
            job_id=job_id,
            linkedin_job_id="j1",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v1",
            ranking_profile_version="v1",
            recommendation="apply_focus",
        )
        questions = [
            LinkedInApplicationQuestion(
                question_key="phone_number",
                prompt_text="Phone number",
                input_type="text",
                required=True,
            )
        ]
        proposals = {
            "phone_number": LinkedInApplicationAnswerProposal(
                question_key="phone_number",
                answer_source="deterministic",
                answer_value="+1-555-0100",
                confidence="high",
                requires_user_input=False,
                reason="From dossier contact.",
            )
        }
        replace_application_questions(
            connection,
            application_id=app_id,
            job_id=job_id,
            linkedin_job_id="j1",
            step_index=1,
            step_name="Contact Info",
            questions=questions,
            proposals_by_key=proposals,
        )
        rows = load_application_questions(connection, app_id)
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["question_key"] == "phone_number"
    assert rows[0]["answer_value"] == "+1-555-0100"
    assert rows[0]["fill_status"] == "filled"
    assert rows[0]["required"] is True


# ---------------------------------------------------------------------------
# mark_job_as_applied_from_confirmation
# ---------------------------------------------------------------------------


def test_mark_applied_creates_application_when_none_exists(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        _seed_job(connection, "j1", stage=JobStage.ENRICHED)
        result = mark_job_as_applied_from_confirmation(
            connection,
            linkedin_job_id="j1",
            application_type="external_apply",
            applied_at="2026-03-31T10:00:00Z",
            confirmation_source="linkedin_confirmation_email",
        )
        job_row = connection.execute("SELECT stage FROM jobs WHERE linkedin_job_id='j1'").fetchone()
        app_row = connection.execute(
            "SELECT status FROM job_applications WHERE linkedin_job_id='j1'"
        ).fetchone()
    finally:
        connection.close()

    assert result["job_found"] is True
    assert result["application_created"] is True
    assert result["application_updated"] is False
    assert job_row["stage"] == JobStage.APPLIED
    assert app_row["status"] == "applied"


def test_mark_applied_updates_existing_application(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        job_id = _seed_job(connection, "j1", stage=JobStage.RANKED)
        create_job_application(
            connection,
            job_id=job_id,
            linkedin_job_id="j1",
            application_type="external_apply",
            ranking_prompt_version="v1",
            ranking_profile_version="v1",
            recommendation="apply_focus",
        )
        result = mark_job_as_applied_from_confirmation(
            connection,
            linkedin_job_id="j1",
            application_type="external_apply",
            applied_at="2026-03-31T10:00:00Z",
            confirmation_source="linkedin_confirmation_email",
        )
    finally:
        connection.close()

    assert result["application_created"] is False
    assert result["application_updated"] is True


def test_mark_applied_returns_job_not_found_for_unknown_job(tmp_path) -> None:
    connection = _make_connection(tmp_path)
    try:
        initialize_schema(connection)
        result = mark_job_as_applied_from_confirmation(
            connection,
            linkedin_job_id="nonexistent",
            application_type="external_apply",
            applied_at="2026-03-31T10:00:00Z",
            confirmation_source="test",
        )
    finally:
        connection.close()

    assert result["job_found"] is False
    assert result["application_created"] is False
