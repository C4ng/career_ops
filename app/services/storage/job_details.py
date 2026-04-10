from __future__ import annotations

import sqlite3

from app.services.storage._shared import load_job_rows_by_stage, now_iso, update_job_by_linkedin_job_id
from app.services.storage.stages import JobStage, validate_stage_transition


def load_triaged_jobs_for_detail_fetch(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = load_job_rows_by_stage(
        connection,
        stage=JobStage.TRIAGED,
        select_columns="id, linkedin_job_id, job_url, title, company, location_text, work_mode",
    )
    return [
        {
            "job_id": int(row["id"]),
            "linkedin_job_id": row["linkedin_job_id"],
            "job_url": row["job_url"],
            "title": row["title"],
            "company": row["company"],
            "location_text": row["location_text"],
            "work_mode": row["work_mode"],
        }
        for row in rows
    ]


NOT_ACCEPTING_STATUS = "No longer accepting applications"


def classify_detail_stage(
    application_status_text: str | None,
) -> tuple[str, str | None]:
    if application_status_text == NOT_ACCEPTING_STATUS:
        return JobStage.NOT_APPLICABLE, application_status_text
    return JobStage.DETAILED, None


def save_job_details(
    connection: sqlite3.Connection,
    details: list[dict[str, object]],
) -> dict[str, int]:
    summary = {
        "details_received": len(details),
        "jobs_updated": 0,
        "jobs_missing": 0,
        "descriptions_saved": 0,
        "descriptions_missing": 0,
        "apply_link_saved": 0,
        "posted_text_saved": 0,
        "work_mode_saved": 0,
        "employment_type_saved": 0,
        "applicant_count_saved": 0,
        "application_status_saved": 0,
    }
    now = now_iso()

    with connection:
        for detail in details:
            job_description = detail.get("job_description")
            apply_link = detail.get("apply_link")
            observed_posted_text = detail.get("observed_posted_text")
            work_mode = detail.get("work_mode")
            employment_type = detail.get("employment_type")
            applicant_count_text = detail.get("applicant_count_text")
            application_status_text = detail.get("application_status_text")
            easy_apply = int(bool(detail.get("easy_apply")))
            to_stage, stage_reason = classify_detail_stage(application_status_text)
            linkedin_job_id = str(detail["linkedin_job_id"])
            current_row = connection.execute(
                "SELECT stage FROM jobs WHERE linkedin_job_id = ?",
                (linkedin_job_id,),
            ).fetchone()
            if current_row is None:
                summary["jobs_missing"] += 1
                continue
            validate_stage_transition(current_row["stage"], to_stage)
            rowcount = update_job_by_linkedin_job_id(
                connection,
                assignments_sql="""
                    job_description = COALESCE(?, job_description),
                    apply_link = COALESCE(?, apply_link),
                    observed_posted_text = COALESCE(?, observed_posted_text),
                    work_mode = COALESCE(?, work_mode),
                    employment_type = COALESCE(?, employment_type),
                    applicant_count_text = COALESCE(?, applicant_count_text),
                    application_status_text = COALESCE(?, application_status_text),
                    easy_apply = CASE WHEN easy_apply = 1 OR ? = 1 THEN 1 ELSE 0 END,
                    stage = ?,
                    stage_reason = ?,
                    stage_updated_at = ?,
                    updated_at = ?
                """,
                values=(
                    job_description,
                    apply_link,
                    observed_posted_text,
                    work_mode,
                    employment_type,
                    applicant_count_text,
                    application_status_text,
                    easy_apply,
                    to_stage,
                    stage_reason,
                    now,
                    now,
                ),
                linkedin_job_id=linkedin_job_id,
            )
            if rowcount == 0:
                summary["jobs_missing"] += 1
                continue
            summary["jobs_updated"] += 1
            if job_description:
                summary["descriptions_saved"] += 1
            else:
                summary["descriptions_missing"] += 1
            if apply_link:
                summary["apply_link_saved"] += 1
            if observed_posted_text:
                summary["posted_text_saved"] += 1
            if work_mode:
                summary["work_mode_saved"] += 1
            if employment_type:
                summary["employment_type_saved"] += 1
            if applicant_count_text:
                summary["applicant_count_saved"] += 1
            if application_status_text:
                summary["application_status_saved"] += 1

    return summary
