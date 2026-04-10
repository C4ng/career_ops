from __future__ import annotations

import json
import logging
import sqlite3

from app.models import LinkedInApplicationAnswerProposal, LinkedInApplicationQuestion
from app.services.storage._shared import now_iso
from app.services.storage.stages import JobStage, validate_stage_transition
from app.services.storage.types import (
    ApplicationQuestionRow,
    ApplicationRow,
    ConfirmationResult,
    RankedJobRow,
    SubmittedPendingApplicationRow,
)


logger = logging.getLogger(__name__)


def load_ranked_easy_apply_jobs(
    connection: sqlite3.Connection,
    limit: int,
    *,
    prompt_version: str,
    profile_version: str,
    recommendations: list[str],
    application_type: str,
) -> list[RankedJobRow]:
    if not recommendations:
        return []

    placeholders = ", ".join("?" for _ in recommendations)
    rows = connection.execute(
        f"""
        SELECT
            j.id,
            j.linkedin_job_id,
            j.job_url,
            j.apply_link,
            j.title,
            j.company,
            j.location_text,
            j.work_mode,
            j.salary_text,
            j.employment_type,
            j.application_status_text,
            j.easy_apply,
            r.recommendation
        FROM jobs j
        JOIN job_rankings r
          ON r.linkedin_job_id = j.linkedin_job_id
        WHERE j.stage = ?
          AND j.easy_apply = 1
          AND r.prompt_version = ?
          AND r.profile_version = ?
          AND r.recommendation IN ({placeholders})
          AND NOT EXISTS (
              SELECT 1
              FROM job_applications a
              WHERE a.linkedin_job_id = j.linkedin_job_id
                AND a.application_type = ?
          )
        ORDER BY j.updated_at DESC, j.id DESC
        LIMIT ?
        """,
        (JobStage.RANKED, prompt_version, profile_version, *recommendations, application_type, limit),
    ).fetchall()
    return [
        {
            "job_id": int(row["id"]),
            "linkedin_job_id": row["linkedin_job_id"],
            "job_url": row["job_url"],
            "apply_link": row["apply_link"],
            "title": row["title"],
            "company": row["company"],
            "location_text": row["location_text"],
            "work_mode": row["work_mode"],
            "salary_text": row["salary_text"],
            "employment_type": row["employment_type"],
            "application_status_text": row["application_status_text"],
            "easy_apply": bool(row["easy_apply"]),
            "recommendation": row["recommendation"],
        }
        for row in rows
    ]


def load_submitted_pending_applications(
    connection: sqlite3.Connection,
    limit: int = 50,
    *,
    application_type: str = "linkedin_easy_apply",
) -> list[SubmittedPendingApplicationRow]:
    rows = connection.execute(
        """
        SELECT
            a.id,
            a.job_id,
            a.linkedin_job_id,
            a.application_type,
            a.status,
            a.last_seen_url,
            a.submitted_at,
            j.job_url,
            j.title,
            j.company
        FROM job_applications a
        JOIN jobs j
          ON j.id = a.job_id
        WHERE a.application_type = ?
          AND a.status = 'submitted_pending_confirmation'
        ORDER BY a.updated_at DESC, a.id DESC
        LIMIT ?
        """,
        (application_type, limit),
    ).fetchall()
    return [
        {
            "application_id": int(row["id"]),
            "job_id": int(row["job_id"]),
            "linkedin_job_id": row["linkedin_job_id"],
            "application_type": row["application_type"],
            "status": row["status"],
            "last_seen_url": row["last_seen_url"],
            "submitted_at": row["submitted_at"],
            "job_url": row["job_url"],
            "title": row["title"],
            "company": row["company"],
        }
        for row in rows
    ]


def create_job_application(
    connection: sqlite3.Connection,
    *,
    job_id: int,
    linkedin_job_id: str,
    application_type: str,
    ranking_prompt_version: str,
    ranking_profile_version: str,
    recommendation: str,
) -> int:
    now = now_iso()
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO job_applications (
                job_id,
                linkedin_job_id,
                application_type,
                ranking_prompt_version,
                ranking_profile_version,
                recommendation,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                linkedin_job_id,
                application_type,
                ranking_prompt_version,
                ranking_profile_version,
                recommendation,
                "opened",
                now,
                now,
            ),
        )
    return int(cursor.lastrowid)


def get_or_create_job_application(
    connection: sqlite3.Connection,
    *,
    job_id: int,
    linkedin_job_id: str,
    application_type: str,
    ranking_prompt_version: str | None = None,
    ranking_profile_version: str | None = None,
    recommendation: str | None = None,
) -> tuple[int, bool]:
    row = connection.execute(
        """
        SELECT id
        FROM job_applications
        WHERE linkedin_job_id = ?
          AND application_type = ?
          AND status != 'applied'
        ORDER BY id DESC
        LIMIT 1
        """,
        (linkedin_job_id, application_type),
    ).fetchone()
    if row is not None:
        return int(row["id"]), False
    return (
        create_job_application(
            connection,
            job_id=job_id,
            linkedin_job_id=linkedin_job_id,
            application_type=application_type,
            ranking_prompt_version=ranking_prompt_version or "",
            ranking_profile_version=ranking_profile_version or "",
            recommendation=recommendation or "",
        ),
        True,
    )


def replace_application_questions(
    connection: sqlite3.Connection,
    *,
    application_id: int,
    job_id: int,
    linkedin_job_id: str,
    step_index: int,
    step_name: str | None,
    questions: list[LinkedInApplicationQuestion],
    proposals_by_key: dict[str, LinkedInApplicationAnswerProposal],
) -> int:
    now = now_iso()
    try:
        with connection:
            connection.execute(
                "DELETE FROM job_application_questions WHERE application_id = ? AND step_index = ?",
                (application_id, step_index),
            )
            for question in questions:
                proposal = proposals_by_key.get(question.question_key)
                try:
                    options_json = json.dumps(question.options, ensure_ascii=False)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Failed to serialize options for question '{question.question_key}' "
                        f"(application_id={application_id}, step_index={step_index}): {exc}"
                    ) from exc
                connection.execute(
                    """
                    INSERT INTO job_application_questions (
                        application_id,
                        job_id,
                        linkedin_job_id,
                        step_index,
                        step_name,
                        question_key,
                        prompt_text,
                        input_type,
                        required,
                        options_json,
                        current_value,
                        field_name,
                        field_id,
                        normalized_intent,
                        answer_source,
                        answer_value,
                        confidence,
                        requires_user_input,
                        reason,
                        fill_status,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        application_id,
                        job_id,
                        linkedin_job_id,
                        step_index,
                        step_name,
                        question.question_key,
                        question.prompt_text,
                        question.input_type,
                        int(question.required),
                        options_json,
                        question.current_value,
                        question.field_name,
                        question.field_id,
                        None,
                        proposal.answer_source if proposal else None,
                        proposal.answer_value if proposal else None,
                        proposal.confidence if proposal else None,
                        int(proposal.requires_user_input) if proposal else 0,
                        proposal.reason if proposal else None,
                        _fill_status_from_proposal(proposal),
                        now,
                        now,
                    ),
                )
    except Exception:
        logger.exception(
            "replace_application_questions failed — transaction rolled back",
            extra={
                "application_id": application_id,
                "job_id": job_id,
                "linkedin_job_id": linkedin_job_id,
                "step_index": step_index,
                "step_name": step_name,
                "question_count": len(questions),
                "proposal_count": len(proposals_by_key),
            },
        )
        raise
    return len(questions)


def _fill_status_from_proposal(proposal: LinkedInApplicationAnswerProposal | None) -> str:
    if proposal is None:
        return "unfilled"
    if proposal.requires_user_input:
        return "needs_user_input"
    if proposal.answer_source == "skip":
        return "skipped"
    if proposal.answer_value:
        return "filled"
    return "unfilled"


def update_job_application_status(
    connection: sqlite3.Connection,
    application_id: int,
    *,
    status: str,
    pause_reason: str | None = None,
    last_error: str | None = None,
    review_step_name: str | None = None,
    last_seen_url: str | None = None,
    last_screenshot_path: str | None = None,
    submitted: bool = False,
    completed: bool = False,
) -> None:
    now = now_iso()
    with connection:
        connection.execute(
            """
            UPDATE job_applications
            SET
                status = ?,
                pause_reason = ?,
                last_error = ?,
                review_step_name = ?,
                last_seen_url = ?,
                last_screenshot_path = ?,
                submitted_at = CASE WHEN ? THEN COALESCE(submitted_at, ?) ELSE submitted_at END,
                updated_at = ?,
                completed_at = CASE WHEN ? THEN ? ELSE completed_at END
            WHERE id = ?
            """,
            (
                status,
                pause_reason,
                last_error,
                review_step_name,
                last_seen_url,
                last_screenshot_path,
                int(submitted),
                now,
                now,
                int(completed),
                now,
                application_id,
            ),
        )


def load_job_application(
    connection: sqlite3.Connection,
    application_id: int,
) -> ApplicationRow | None:
    row = connection.execute(
        """
        SELECT
            id,
            job_id,
            linkedin_job_id,
            application_type,
            status,
            review_step_name,
            last_seen_url,
            last_screenshot_path,
            submitted_at
        FROM job_applications
        WHERE id = ?
        """,
        (application_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "application_id": int(row["id"]),
        "job_id": int(row["job_id"]),
        "linkedin_job_id": row["linkedin_job_id"],
        "application_type": row["application_type"],
        "status": row["status"],
        "review_step_name": row["review_step_name"],
        "last_seen_url": row["last_seen_url"],
        "last_screenshot_path": row["last_screenshot_path"],
        "submitted_at": row["submitted_at"],
    }


def load_application_questions(
    connection: sqlite3.Connection,
    application_id: int,
) -> list[ApplicationQuestionRow]:
    rows = connection.execute(
        """
        SELECT
            id,
            step_index,
            step_name,
            question_key,
            prompt_text,
            input_type,
            required,
            options_json,
            current_value,
            field_name,
            field_id,
            answer_source,
            answer_value,
            confidence,
            requires_user_input,
            reason,
            fill_status
        FROM job_application_questions
        WHERE application_id = ?
        ORDER BY step_index ASC, id ASC
        """,
        (application_id,),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "step_index": int(row["step_index"]),
            "step_name": row["step_name"],
            "question_key": row["question_key"],
            "prompt_text": row["prompt_text"],
            "input_type": row["input_type"],
            "required": bool(row["required"]),
            "options": json.loads(row["options_json"]) if row["options_json"] else [],
            "current_value": row["current_value"],
            "field_name": row["field_name"],
            "field_id": row["field_id"],
            "answer_source": row["answer_source"],
            "answer_value": row["answer_value"],
            "confidence": row["confidence"],
            "requires_user_input": bool(row["requires_user_input"]),
            "reason": row["reason"],
            "fill_status": row["fill_status"],
        }
        for row in rows
    ]


def update_application_question_answer(
    connection: sqlite3.Connection,
    *,
    application_id: int,
    question_key: str,
    answer_value: str,
    answer_source: str = "deterministic",
    confidence: str = "high",
    reason: str = "Updated during human review.",
) -> None:
    now = now_iso()
    with connection:
        connection.execute(
            """
            UPDATE job_application_questions
            SET
                answer_source = ?,
                answer_value = ?,
                confidence = ?,
                requires_user_input = 0,
                reason = ?,
                fill_status = 'filled',
                updated_at = ?
            WHERE application_id = ?
              AND question_key = ?
            """,
            (
                answer_source,
                answer_value,
                confidence,
                reason,
                now,
                application_id,
                question_key,
            ),
        )


def mark_job_as_applied_from_confirmation(
    connection: sqlite3.Connection,
    *,
    linkedin_job_id: str,
    application_type: str = "linkedin_easy_apply",
    applied_at: str,
    confirmation_source: str,
    last_seen_url: str | None = None,
) -> ConfirmationResult:
    now = now_iso()
    application_created = False
    application_updated = False
    with connection:
        job_row = connection.execute(
            """
            SELECT id, job_url, stage
            FROM jobs
            WHERE linkedin_job_id = ?
            """,
            (linkedin_job_id,),
        ).fetchone()
        if job_row is None:
            return {
                "linkedin_job_id": linkedin_job_id,
                "job_found": False,
                "application_created": False,
                "application_updated": False,
                "job_updated": False,
            }
        validate_stage_transition(job_row["stage"], JobStage.APPLIED)

        job_id = int(job_row["id"])
        job_url = job_row["job_url"]
        application_row = connection.execute(
            """
            SELECT id
            FROM job_applications
            WHERE linkedin_job_id = ?
              AND application_type = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (linkedin_job_id, application_type),
        ).fetchone()
        if application_row is None:
            connection.execute(
                """
                INSERT INTO job_applications (
                    job_id,
                    linkedin_job_id,
                    application_type,
                    status,
                    last_seen_url,
                    submitted_at,
                    created_at,
                    updated_at,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    linkedin_job_id,
                    application_type,
                    "applied",
                    last_seen_url or job_url,
                    applied_at,
                    applied_at,
                    now,
                    applied_at,
                ),
            )
            application_created = True
        else:
            connection.execute(
                """
                UPDATE job_applications
                SET
                    status = 'applied',
                    pause_reason = NULL,
                    last_error = NULL,
                    review_step_name = NULL,
                    last_seen_url = COALESCE(?, last_seen_url),
                    updated_at = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    last_seen_url,
                    now,
                    applied_at,
                    int(application_row["id"]),
                ),
            )
            application_updated = True

        job_updated = bool(
            connection.execute(
                """
                UPDATE jobs
                SET
                    stage = ?,
                    stage_reason = ?,
                    stage_updated_at = ?,
                    applied_at = ?,
                    updated_at = ?
                WHERE linkedin_job_id = ?
                """,
                (
                    JobStage.APPLIED,
                    confirmation_source,
                    applied_at,
                    applied_at,
                    now,
                    linkedin_job_id,
                ),
            ).rowcount
        )

    return {
        "linkedin_job_id": linkedin_job_id,
        "job_found": True,
        "application_created": application_created,
        "application_updated": application_updated,
        "job_updated": job_updated,
    }


def mark_job_as_applied_from_confirmation_email(
    connection: sqlite3.Connection,
    *,
    linkedin_job_id: str,
    application_type: str = "external_apply",
    applied_at: str,
    confirmation_source: str = "linkedin_confirmation_email",
    last_seen_url: str | None = None,
) -> dict[str, object]:
    if application_type == "linkedin_easy_apply":
        raise ValueError("Email confirmation is disabled for linkedin_easy_apply; use LinkedIn My Jobs UI confirmation.")
    return mark_job_as_applied_from_confirmation(
        connection,
        linkedin_job_id=linkedin_job_id,
        application_type=application_type,
        applied_at=applied_at,
        confirmation_source=confirmation_source,
        last_seen_url=last_seen_url,
    )
