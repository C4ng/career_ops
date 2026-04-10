from __future__ import annotations

import json
import sqlite3

from app.models import LinkedInJobCard
from app.services.storage._shared import serialize_to_json_or_none, now_iso, observed_at_value
from app.services.storage.stages import JobStage


def _job_card_skip_reason(job_card: LinkedInJobCard) -> str | None:
    missing_fields: list[str] = []
    if not job_card.linkedin_job_id:
        missing_fields.append("linkedin_job_id")
    if not job_card.job_url:
        missing_fields.append("job_url")
    if not job_card.title:
        missing_fields.append("title")
    if not job_card.company:
        missing_fields.append("company")
    if missing_fields:
        return f"missing_required_fields:{','.join(missing_fields)}"
    return None


def _job_card_badges_json(job_card: LinkedInJobCard) -> str:
    return json.dumps(job_card.badges, ensure_ascii=False)


def upsert_job(connection: sqlite3.Connection, job_card: LinkedInJobCard) -> tuple[int, bool]:
    now = now_iso()
    existing = connection.execute(
        "SELECT id FROM jobs WHERE linkedin_job_id = ?",
        (job_card.linkedin_job_id,),
    ).fetchone()

    requirements_json = serialize_to_json_or_none(
        job_card.requirements.model_dump(mode="json") if job_card.requirements else None
    )
    company_intro_json = serialize_to_json_or_none(job_card.company_intro)
    role_scope_json = serialize_to_json_or_none(job_card.role_scope)
    benefits_json = serialize_to_json_or_none(job_card.benefits)
    application_details_json = serialize_to_json_or_none(job_card.application_details)

    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO jobs (
                linkedin_job_id,
                job_url,
                apply_link,
                title,
                company,
                location_text,
                work_mode,
                observed_posted_text,
                salary_text,
                job_description,
                company_intro,
                role_scope,
                requirements,
                benefits,
                application_details,
                employment_type,
                applicant_count_text,
                application_status_text,
                easy_apply,
                stage,
                stage_reason,
                stage_updated_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_card.linkedin_job_id,
                job_card.job_url,
                job_card.apply_link,
                job_card.title,
                job_card.company,
                job_card.location_text,
                job_card.work_mode,
                job_card.observed_posted_text,
                job_card.salary_text,
                job_card.job_description,
                company_intro_json,
                role_scope_json,
                requirements_json,
                benefits_json,
                application_details_json,
                job_card.employment_type,
                job_card.applicant_count_text,
                job_card.application_status_text,
                int(job_card.easy_apply),
                JobStage.DISCOVERED,
                None,
                now,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid), True

    job_id = int(existing["id"])
    connection.execute(
        """
        UPDATE jobs
        SET
            job_url = ?,
            apply_link = COALESCE(?, apply_link),
            title = ?,
            company = ?,
            location_text = COALESCE(?, location_text),
            work_mode = COALESCE(?, work_mode),
            observed_posted_text = COALESCE(?, observed_posted_text),
            salary_text = COALESCE(?, salary_text),
            job_description = COALESCE(?, job_description),
            company_intro = COALESCE(?, company_intro),
            role_scope = COALESCE(?, role_scope),
            requirements = COALESCE(?, requirements),
            benefits = COALESCE(?, benefits),
            application_details = COALESCE(?, application_details),
            employment_type = COALESCE(?, employment_type),
            applicant_count_text = COALESCE(?, applicant_count_text),
            application_status_text = COALESCE(?, application_status_text),
            easy_apply = CASE WHEN easy_apply = 1 OR ? = 1 THEN 1 ELSE 0 END,
            stage = COALESCE(stage, 'discovered'),
            stage_reason = CASE WHEN stage IS NULL THEN NULL ELSE stage_reason END,
            stage_updated_at = COALESCE(stage_updated_at, ?),
            updated_at = ?
        WHERE id = ?
        """,
        (
            job_card.job_url,
            job_card.apply_link,
            job_card.title,
            job_card.company,
            job_card.location_text,
            job_card.work_mode,
            job_card.observed_posted_text,
            job_card.salary_text,
            job_card.job_description,
            company_intro_json,
            role_scope_json,
            requirements_json,
            benefits_json,
            application_details_json,
            job_card.employment_type,
            job_card.applicant_count_text,
            job_card.application_status_text,
            int(job_card.easy_apply),
            now,
            now,
            job_id,
        ),
    )
    return job_id, False


def insert_job_observation(connection: sqlite3.Connection, job_id: int, job_card: LinkedInJobCard) -> bool:
    observed_at = observed_at_value(job_card)
    existing = connection.execute(
        """
        SELECT id
        FROM job_observations
        WHERE job_id = ?
          AND source_type = ?
          AND COALESCE(observed_at, '') = COALESCE(?, '')
          AND COALESCE(job_url, '') = COALESCE(?, '')
          AND title = ?
          AND company = ?
        """,
        (
            job_id,
            job_card.source_type,
            observed_at,
            job_card.job_url,
            job_card.title,
            job_card.company,
        ),
    ).fetchone()
    if existing is not None:
        return False

    connection.execute(
        """
        INSERT INTO job_observations (
            job_id,
            linkedin_job_id,
            source_type,
            observed_at,
            job_url,
            title,
            company,
            location_text,
            work_mode,
            observed_posted_text,
            salary_text,
            easy_apply,
            badges,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            job_card.linkedin_job_id,
            job_card.source_type,
            observed_at,
            job_card.job_url,
            job_card.title,
            job_card.company,
            job_card.location_text,
            job_card.work_mode,
            job_card.observed_posted_text,
            job_card.salary_text,
            int(job_card.easy_apply),
            _job_card_badges_json(job_card),
            now_iso(),
        ),
    )
    return True


def persist_linkedin_job_cards(
    connection: sqlite3.Connection,
    job_cards: list[LinkedInJobCard],
) -> dict[str, object]:
    summary = {
        "cards_read": len(job_cards),
        "jobs_inserted": 0,
        "jobs_updated": 0,
        "observations_inserted": 0,
        "observations_skipped": 0,
        "cards_skipped": 0,
        "skip_reasons": {},
    }

    with connection:
        for job_card in job_cards:
            skip_reason = _job_card_skip_reason(job_card)
            if skip_reason:
                summary["cards_skipped"] += 1
                summary["skip_reasons"][skip_reason] = summary["skip_reasons"].get(skip_reason, 0) + 1
                continue

            job_id, inserted = upsert_job(connection, job_card)
            if inserted:
                summary["jobs_inserted"] += 1
            else:
                summary["jobs_updated"] += 1

            if insert_job_observation(connection, job_id, job_card):
                summary["observations_inserted"] += 1
            else:
                summary["observations_skipped"] += 1

    return summary
