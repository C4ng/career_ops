from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from app.models import LinkedInApplicationAnswerProposal, LinkedInApplicationQuestion
from app.services.storage.applications import (
    create_job_application,
    get_or_create_job_application,
    load_application_questions,
    load_job_application,
    load_ranked_easy_apply_jobs,
    load_submitted_pending_applications,
    mark_job_as_applied_from_confirmation,
    mark_job_as_applied_from_confirmation_email,
    replace_application_questions,
    update_application_question_answer,
    update_job_application_status,
)
from app.services.storage.db import connect_sqlite, initialize_schema
from app.services.storage.stages import JobStage
from app.services.storage.email_confirmations import (
    build_confirmation_dedupe_key,
    process_confirmation_emails,
)


def _insert_job(connection, *, linkedin_job_id: str, stage: str = JobStage.RANKED, easy_apply: int = 1) -> None:
    connection.execute(
        """
        INSERT INTO jobs (
            linkedin_job_id, job_url, title, company, location_text, easy_apply,
            stage, stage_reason, stage_updated_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            linkedin_job_id,
            f"https://www.linkedin.com/jobs/view/{linkedin_job_id}/",
            "AI Engineer",
            "Example",
            "Toronto, ON",
            easy_apply,
            stage,
            None,
            None,
            "2026-03-29T00:00:00Z",
            "2026-03-29T00:00:00Z",
        ),
    )


def _insert_ranking(connection, *, linkedin_job_id: str, recommendation: str = "apply_auto") -> None:
    job_id = connection.execute("SELECT id FROM jobs WHERE linkedin_job_id = ?", (linkedin_job_id,)).fetchone()[0]
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
            job_id,
            linkedin_job_id,
            "gemini-2.5-flash",
            "v7",
            "v2",
            "strong",
            "Good role fit",
            "appropriate",
            "Good level fit",
            "preferred",
            "Good preference fit",
            recommendation,
            "Worth applying.",
            "2026-03-29T00:00:00Z",
        ),
    )


def test_load_ranked_easy_apply_jobs_filters_by_recommendation_and_existing_attempt(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", easy_apply=1)
        _insert_job(connection, linkedin_job_id="456", easy_apply=1)
        _insert_job(connection, linkedin_job_id="789", easy_apply=0)
        _insert_ranking(connection, linkedin_job_id="123", recommendation="apply_auto")
        _insert_ranking(connection, linkedin_job_id="456", recommendation="low_priority")
        _insert_ranking(connection, linkedin_job_id="789", recommendation="apply_auto")
        application_id = create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="123",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )
        assert application_id > 0

        rows = load_ranked_easy_apply_jobs(
            connection,
            10,
            prompt_version="v6",
            profile_version="v2",
            recommendations=["apply_auto"],
            application_type="linkedin_easy_apply",
        )
    finally:
        connection.close()

    assert rows == []


def test_load_submitted_pending_applications_filters_status(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", easy_apply=1)
        _insert_job(connection, linkedin_job_id="456", easy_apply=1)
        first_id = create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="123",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )
        second_id = create_job_application(
            connection,
            job_id=2,
            linkedin_job_id="456",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )
        update_job_application_status(connection, first_id, status="submitted_pending_confirmation", submitted=True)
        update_job_application_status(connection, second_id, status="review_ready")

        rows = load_submitted_pending_applications(connection)
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["application_id"] == first_id
    assert rows[0]["job_id"] == 1
    assert rows[0]["linkedin_job_id"] == "123"
    assert rows[0]["application_type"] == "linkedin_easy_apply"
    assert rows[0]["status"] == "submitted_pending_confirmation"
    assert rows[0]["last_seen_url"] is None
    assert rows[0]["submitted_at"] is not None
    assert rows[0]["job_url"] == "https://www.linkedin.com/jobs/view/123/"
    assert rows[0]["title"] == "AI Engineer"
    assert rows[0]["company"] == "Example"


def test_replace_application_questions_and_status_update(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", easy_apply=1)
        _insert_ranking(connection, linkedin_job_id="123", recommendation="apply_auto")
        application_id = create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="123",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )

        question = LinkedInApplicationQuestion(
            question_key="email",
            prompt_text="Email address",
            input_type="email",
            required=True,
        )
        proposal = LinkedInApplicationAnswerProposal(
            question_key="email",
            answer_source="deterministic",
            answer_value="user@example.com",
            confidence="high",
            requires_user_input=False,
            reason="Matched dossier email.",
        )
        replace_application_questions(
            connection,
            application_id=application_id,
            job_id=1,
            linkedin_job_id="123",
            step_index=1,
            step_name="Contact info",
            questions=[question],
            proposals_by_key={"email": proposal},
        )
        update_job_application_status(
            connection,
            application_id,
            status="needs_user_input",
            pause_reason="Need phone number.",
            last_seen_url="https://www.linkedin.com/jobs/view/123/",
            last_screenshot_path="data/screenshots/easy_apply/123.step1.png",
        )

        question_row = connection.execute(
            """
            SELECT question_key, normalized_intent, answer_source, answer_value, confidence, requires_user_input, fill_status
            FROM job_application_questions
            WHERE application_id = ?
            """,
            (application_id,),
        ).fetchone()
        application_row = connection.execute(
            """
            SELECT status, pause_reason, last_seen_url, last_screenshot_path, submitted_at
            FROM job_applications
            WHERE id = ?
            """,
            (application_id,),
        ).fetchone()
    finally:
        connection.close()

    assert tuple(question_row) == ("email", None, "deterministic", "user@example.com", "high", 0, "filled")
    assert tuple(application_row) == (
        "needs_user_input",
        "Need phone number.",
        "https://www.linkedin.com/jobs/view/123/",
        "data/screenshots/easy_apply/123.step1.png",
        None,
    )


def test_get_or_create_job_application_reuses_open_session(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", easy_apply=1)
        first_id, first_created = get_or_create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="123",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )
        second_id, second_created = get_or_create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="123",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )
    finally:
        connection.close()

    assert first_created is True
    assert second_created is False
    assert first_id == second_id


def test_load_application_questions_and_update_answer_persists_field_metadata(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", easy_apply=1)
        application_id = create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="123",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )
        question = LinkedInApplicationQuestion(
            question_key="english_proficiency",
            prompt_text="What is your level of proficiency in English?",
            input_type="select_one",
            required=True,
            options=["None", "Conversational", "Professional", "Native or bilingual"],
            field_name="englishProficiency",
            field_id="english-proficiency-select",
        )
        proposal = LinkedInApplicationAnswerProposal(
            question_key="english_proficiency",
            answer_source="user_required",
            answer_value=None,
            confidence="low",
            requires_user_input=True,
            reason="Missing candidate answer.",
        )
        replace_application_questions(
            connection,
            application_id=application_id,
            job_id=1,
            linkedin_job_id="123",
            step_index=3,
            step_name="Additional Questions",
            questions=[question],
            proposals_by_key={"english_proficiency": proposal},
        )
        update_application_question_answer(
            connection,
            application_id=application_id,
            question_key="english_proficiency",
            answer_value="Professional",
        )
        rows = load_application_questions(connection, application_id)
        application = load_job_application(connection, application_id)
    finally:
        connection.close()

    assert application is not None
    assert rows == [
        {
            "id": 1,
            "step_index": 3,
            "step_name": "Additional Questions",
            "question_key": "english_proficiency",
            "prompt_text": "What is your level of proficiency in English?",
            "input_type": "select_one",
            "required": True,
            "options": ["None", "Conversational", "Professional", "Native or bilingual"],
            "current_value": None,
            "field_name": "englishProficiency",
            "field_id": "english-proficiency-select",
            "answer_source": "deterministic",
            "answer_value": "Professional",
            "confidence": "high",
            "requires_user_input": False,
            "reason": "Updated during human review.",
            "fill_status": "filled",
        }
    ]


def test_mark_job_as_applied_from_confirmation_email_updates_existing_application_and_job(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage=JobStage.RANKED, easy_apply=1)
        application_id = create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="123",
            application_type="external_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )

        summary = mark_job_as_applied_from_confirmation_email(
            connection,
            linkedin_job_id="123",
            application_type="external_apply",
            applied_at="2026-03-30T21:02:00-04:00",
            last_seen_url="https://www.linkedin.com/jobs/view/123/",
        )

        application_row = connection.execute(
            """
            SELECT status, last_seen_url, submitted_at, completed_at
            FROM job_applications
            WHERE id = ?
            """,
            (application_id,),
        ).fetchone()
        job_row = connection.execute(
            """
            SELECT stage, stage_reason, applied_at
            FROM jobs
            WHERE linkedin_job_id = '123'
            """
        ).fetchone()
    finally:
        connection.close()

    assert summary == {
        "linkedin_job_id": "123",
        "job_found": True,
        "application_created": False,
        "application_updated": True,
        "job_updated": True,
    }
    assert tuple(application_row) == (
        "applied",
        "https://www.linkedin.com/jobs/view/123/",
        None,
        "2026-03-30T21:02:00-04:00",
    )
    assert tuple(job_row) == (
        "applied",
        "linkedin_confirmation_email",
        "2026-03-30T21:02:00-04:00",
    )


def test_mark_job_as_applied_from_confirmation_supports_ui_source(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage=JobStage.RANKED, easy_apply=1)
        create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="123",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )

        summary = mark_job_as_applied_from_confirmation(
            connection,
            linkedin_job_id="123",
            applied_at="2026-03-30T21:02:00-04:00",
            confirmation_source="linkedin_job_page_ui",
            last_seen_url="https://www.linkedin.com/jobs/view/123/",
        )

        job_row = connection.execute(
            "SELECT stage, stage_reason, applied_at FROM jobs WHERE linkedin_job_id = '123'"
        ).fetchone()
    finally:
        connection.close()

    assert summary["job_updated"] is True
    assert tuple(job_row) == (
        "applied",
        "linkedin_job_page_ui",
        "2026-03-30T21:02:00-04:00",
    )


def test_mark_job_as_applied_from_confirmation_email_backfills_application_when_missing(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage=JobStage.RANKED, easy_apply=1)

        summary = mark_job_as_applied_from_confirmation_email(
            connection,
            linkedin_job_id="123",
            application_type="external_apply",
            applied_at="2026-03-30T21:02:00-04:00",
        )

        application_row = connection.execute(
            """
            SELECT application_type, status, submitted_at, completed_at
            FROM job_applications
            WHERE linkedin_job_id = '123'
            """
        ).fetchone()
    finally:
        connection.close()

    assert summary == {
        "linkedin_job_id": "123",
        "job_found": True,
        "application_created": True,
        "application_updated": False,
        "job_updated": True,
    }
    assert tuple(application_row) == (
        "external_apply",
        "applied",
        "2026-03-30T21:02:00-04:00",
        "2026-03-30T21:02:00-04:00",
    )


def test_mark_job_as_applied_from_confirmation_email_rejects_easy_apply(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage=JobStage.RANKED, easy_apply=1)
        with pytest.raises(ValueError, match="disabled for linkedin_easy_apply"):
            mark_job_as_applied_from_confirmation_email(
                connection,
                linkedin_job_id="123",
                application_type="linkedin_easy_apply",
                applied_at="2026-03-30T21:02:00-04:00",
            )
    finally:
        connection.close()


def test_update_job_application_status_records_submitted_at_without_completing(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", easy_apply=1)
        application_id = create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="123",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )
        update_job_application_status(
            connection,
            application_id,
            status="submitted_pending_confirmation",
            submitted=True,
            completed=False,
        )
        row = connection.execute(
            """
            SELECT status, submitted_at, completed_at
            FROM job_applications
            WHERE id = ?
            """,
            (application_id,),
        ).fetchone()
    finally:
        connection.close()

    assert row[0] == "submitted_pending_confirmation"
    assert row[1] is not None
    assert row[2] is None


def test_process_confirmation_emails_is_idempotent(tmp_path) -> None:
    from app.models import LinkedInApplicationConfirmation

    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="123", stage=JobStage.RANKED, easy_apply=1)
        confirmation = LinkedInApplicationConfirmation(
            sequence_id="1",
            message_id="<confirmation-1@example.com>",
            from_address="jobs-noreply@linkedin.com",
            received_at="2026-03-30T21:02:00-04:00",
            linkedin_job_id="123",
            job_url="https://www.linkedin.com/jobs/view/123/",
            company="Example",
            title="AI Engineer",
        )

        first_summary = process_confirmation_emails(
            connection,
            [confirmation],
            application_type="external_apply",
        )
        second_summary = process_confirmation_emails(
            connection,
            [confirmation],
            application_type="external_apply",
        )

        processed_row = connection.execute(
            """
            SELECT dedupe_key, processing_result, application_created, application_updated, job_updated
            FROM processed_linkedin_confirmation_emails
            """
        ).fetchone()
        application_row = connection.execute(
            """
            SELECT status, completed_at
            FROM job_applications
            WHERE linkedin_job_id = '123'
            """
        ).fetchone()
    finally:
        connection.close()

    assert first_summary["newly_processed"] == 1
    assert first_summary["already_processed"] == 0
    assert second_summary["newly_processed"] == 0
    assert second_summary["already_processed"] == 1
    assert tuple(processed_row) == (
        build_confirmation_dedupe_key(confirmation),
        "processed",
        1,
        0,
        1,
    )
    assert application_row[0] == "applied"
    assert application_row[1] == "2026-03-30T21:02:00-04:00"


def test_process_confirmation_emails_rejects_easy_apply_policy(tmp_path) -> None:
    from app.models import LinkedInApplicationConfirmation

    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        confirmation = LinkedInApplicationConfirmation(
            sequence_id="1",
            message_id="<confirmation-1@example.com>",
            from_address="jobs-noreply@linkedin.com",
            received_at="2026-03-30T21:02:00-04:00",
            linkedin_job_id="123",
            job_url="https://www.linkedin.com/jobs/view/123/",
            company="Example",
            title="AI Engineer",
        )
        with pytest.raises(ValueError, match="disabled for linkedin_easy_apply"):
            process_confirmation_emails(
                connection,
                [confirmation],
                application_type="linkedin_easy_apply",
            )
    finally:
        connection.close()


# --- replace_application_questions: error handling (Issue #2) ---


def _make_question(key: str = "email") -> LinkedInApplicationQuestion:
    return LinkedInApplicationQuestion(
        question_key=key,
        prompt_text="Email address",
        input_type="email",
        required=True,
    )


def _make_proposal(key: str = "email") -> LinkedInApplicationAnswerProposal:
    return LinkedInApplicationAnswerProposal(
        question_key=key,
        answer_source="deterministic",
        answer_value="user@example.com",
        confidence="high",
        requires_user_input=False,
        reason="Matched dossier.",
    )


def test_replace_application_questions_rolls_back_and_preserves_existing_on_failure(tmp_path) -> None:
    """If the replace fails mid-way, the original questions must still be present."""
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="111", easy_apply=1)
        application_id = create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="111",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )
        # Insert a question that should survive the failed replace
        replace_application_questions(
            connection,
            application_id=application_id,
            job_id=1,
            linkedin_job_id="111",
            step_index=0,
            step_name="Contact",
            questions=[_make_question("email")],
            proposals_by_key={"email": _make_proposal("email")},
        )

        # Patch json.dumps inside the applications module to fail on the second call
        # (first call is for serializing options of the first question)
        call_count = {"n": 0}
        real_dumps = __import__("json").dumps

        def failing_dumps(obj, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError("simulated serialization failure")
            return real_dumps(obj, **kwargs)

        with patch("app.services.storage.applications.json.dumps", side_effect=failing_dumps):
            with pytest.raises(ValueError, match="simulated serialization failure"):
                replace_application_questions(
                    connection,
                    application_id=application_id,
                    job_id=1,
                    linkedin_job_id="111",
                    step_index=0,
                    step_name="Contact",
                    questions=[_make_question("email")],
                    proposals_by_key={"email": _make_proposal("email")},
                )

        # Original question must still be there — transaction was rolled back
        surviving = connection.execute(
            "SELECT question_key FROM job_application_questions WHERE application_id = ?",
            (application_id,),
        ).fetchall()
    finally:
        connection.close()

    assert len(surviving) == 1
    assert surviving[0][0] == "email"


def test_replace_application_questions_logs_context_on_failure(tmp_path, caplog) -> None:
    """The logger must emit structured context (application_id, step_index, etc.) on failure."""
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="222", easy_apply=1)
        application_id = create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="222",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )

        with caplog.at_level(logging.ERROR, logger="app.services.storage.applications"):
            with patch(
                "app.services.storage.applications.json.dumps",
                side_effect=ValueError("boom"),
            ):
                with pytest.raises(ValueError):
                    replace_application_questions(
                        connection,
                        application_id=application_id,
                        job_id=1,
                        linkedin_job_id="222",
                        step_index=2,
                        step_name="Skills",
                        questions=[_make_question()],
                        proposals_by_key={},
                    )
    finally:
        connection.close()

    assert any("replace_application_questions failed" in r.message for r in caplog.records)
    # Structured context must be present in the log record's extra
    error_record = next(r for r in caplog.records if "replace_application_questions failed" in r.message)
    assert error_record.application_id == application_id
    assert error_record.linkedin_job_id == "222"
    assert error_record.step_index == 2


def test_mark_job_as_applied_from_confirmation_reads_inside_transaction(tmp_path) -> None:
    """All reads and writes happen in the same transaction — no TOCTOU gap."""
    connection = connect_sqlite(tmp_path / "job.sqlite3")
    try:
        initialize_schema(connection)
        _insert_job(connection, linkedin_job_id="333", easy_apply=1)
        application_id = create_job_application(
            connection,
            job_id=1,
            linkedin_job_id="333",
            application_type="linkedin_easy_apply",
            ranking_prompt_version="v6",
            ranking_profile_version="v2",
            recommendation="apply_auto",
        )

        summary = mark_job_as_applied_from_confirmation(
            connection,
            linkedin_job_id="333",
            applied_at="2026-03-31T10:00:00Z",
            confirmation_source="linkedin_confirmation_email",
        )

        job_row = connection.execute(
            "SELECT stage FROM jobs WHERE linkedin_job_id = '333'"
        ).fetchone()
        application_row = connection.execute(
            "SELECT status FROM job_applications WHERE id = ?", (application_id,)
        ).fetchone()
    finally:
        connection.close()

    assert summary["job_found"] is True
    assert summary["application_updated"] is True
    assert summary["job_updated"] is True
    assert job_row[0] == "applied"
    assert application_row[0] == "applied"
