from __future__ import annotations

import sqlite3

from app.services.storage._shared import (
    serialize_to_json_or_none,
    load_job_rows_by_stage,
    now_iso,
    requirements_has_content,
    update_job_by_linkedin_job_id,
)
from app.services.storage.stages import JobStage, validate_stage_transition


def load_detailed_jobs_for_enrichment(connection: sqlite3.Connection, limit: int) -> list[dict[str, object]]:
    rows = load_job_rows_by_stage(
        connection,
        stage=JobStage.DETAILED,
        select_columns="""
            id,
            linkedin_job_id,
            job_url,
            apply_link,
            title,
            company,
            location_text,
            work_mode,
            observed_posted_text,
            employment_type,
            applicant_count_text,
            application_status_text,
            easy_apply,
            job_description
        """,
        limit=limit,
    )
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
            "observed_posted_text": row["observed_posted_text"],
            "employment_type": row["employment_type"],
            "applicant_count_text": row["applicant_count_text"],
            "application_status_text": row["application_status_text"],
            "easy_apply": bool(row["easy_apply"]),
            "job_description": row["job_description"],
        }
        for row in rows
    ]


def save_job_enrichments(
    connection: sqlite3.Connection,
    enrichments: list[dict[str, object]],
) -> dict[str, int]:
    summary = {
        "enrichments_received": len(enrichments),
        "jobs_updated": 0,
        "jobs_missing": 0,
        "work_mode_saved": 0,
        "salary_text_saved": 0,
        "employment_type_saved": 0,
        "company_intro_saved": 0,
        "role_scope_saved": 0,
        "requirements_saved": 0,
        "benefits_saved": 0,
        "application_details_saved": 0,
    }
    now = now_iso()

    with connection:
        for enrichment in enrichments:
            work_mode = enrichment.get("work_mode")
            salary_text = enrichment.get("salary_text")
            employment_type = enrichment.get("employment_type")
            company_intro = enrichment.get("company_intro") or []
            role_scope = enrichment.get("role_scope") or []
            requirements = enrichment.get("requirements")
            benefits = enrichment.get("benefits") or []
            application_details = enrichment.get("application_details") or []
            linkedin_job_id = str(enrichment["linkedin_job_id"])
            current_row = connection.execute(
                "SELECT stage FROM jobs WHERE linkedin_job_id = ?",
                (linkedin_job_id,),
            ).fetchone()
            if current_row is None:
                summary["jobs_missing"] += 1
                continue
            validate_stage_transition(current_row["stage"], JobStage.ENRICHED)
            rowcount = update_job_by_linkedin_job_id(
                connection,
                assignments_sql="""
                    work_mode = COALESCE(?, work_mode),
                    salary_text = COALESCE(?, salary_text),
                    employment_type = COALESCE(?, employment_type),
                    company_intro = ?,
                    role_scope = ?,
                    requirements = ?,
                    benefits = ?,
                    application_details = ?,
                    stage = ?,
                    stage_reason = NULL,
                    stage_updated_at = ?,
                    updated_at = ?
                """,
                values=(
                    work_mode,
                    salary_text,
                    employment_type,
                    serialize_to_json_or_none(company_intro),
                    serialize_to_json_or_none(role_scope),
                    serialize_to_json_or_none(requirements),
                    serialize_to_json_or_none(benefits),
                    serialize_to_json_or_none(application_details),
                    JobStage.ENRICHED,
                    now,
                    now,
                ),
                linkedin_job_id=linkedin_job_id,
            )
            if rowcount == 0:
                summary["jobs_missing"] += 1
                continue
            summary["jobs_updated"] += 1
            if work_mode:
                summary["work_mode_saved"] += 1
            if salary_text:
                summary["salary_text_saved"] += 1
            if employment_type:
                summary["employment_type_saved"] += 1
            if company_intro:
                summary["company_intro_saved"] += 1
            if role_scope:
                summary["role_scope_saved"] += 1
            if requirements_has_content(requirements):
                summary["requirements_saved"] += 1
            if benefits:
                summary["benefits_saved"] += 1
            if application_details:
                summary["application_details_saved"] += 1

    return summary
