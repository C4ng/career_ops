from __future__ import annotations

import json
import sqlite3

from app.models import LinkedInJobRankingResult
from app.services.storage._shared import now_iso, update_job_by_linkedin_job_id
from app.services.storage.stages import JobStage, validate_stage_transition


def _parse_json_with_fallback(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _default_requirements_template() -> dict[str, list[object]]:
    return {
        "summary": [],
        "skills": [],
        "experience": [],
        "tech": [],
        "education": [],
        "constraints": [],
        "other": [],
    }


def _row_to_ranking_input(row: sqlite3.Row) -> dict[str, object]:
    return {
        "job_id": int(row["id"]),
        "linkedin_job_id": row["linkedin_job_id"],
        "job_url": row["job_url"],
        "apply_link": row["apply_link"],
        "title": row["title"],
        "company": row["company"],
        "location_text": row["location_text"],
        "work_mode": row["work_mode"],
        "observed_posted_text": row["observed_posted_text"],
        "salary_text": row["salary_text"],
        "employment_type": row["employment_type"],
        "applicant_count_text": row["applicant_count_text"],
        "application_status_text": row["application_status_text"],
        "easy_apply": bool(row["easy_apply"]),
        "company_intro": _parse_json_with_fallback(row["company_intro"], []),
        "role_scope": _parse_json_with_fallback(row["role_scope"], []),
        "requirements": _parse_json_with_fallback(row["requirements"], _default_requirements_template()),
        "benefits": _parse_json_with_fallback(row["benefits"], []),
        "application_details": _parse_json_with_fallback(row["application_details"], []),
    }


def load_enriched_jobs_for_ranking(
    connection: sqlite3.Connection,
    limit: int,
    *,
    prompt_version: str,
    profile_version: str,
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT
            j.id,
            j.linkedin_job_id,
            j.job_url,
            j.apply_link,
            j.title,
            j.company,
            j.location_text,
            j.work_mode,
            j.observed_posted_text,
            j.salary_text,
            j.employment_type,
            j.applicant_count_text,
            j.application_status_text,
            j.easy_apply,
            j.company_intro,
            j.role_scope,
            j.requirements,
            j.benefits,
            j.application_details
        FROM jobs j
        WHERE j.stage = ?
          AND NOT EXISTS (
              SELECT 1
              FROM job_rankings r
              WHERE r.linkedin_job_id = j.linkedin_job_id
                AND r.prompt_version = ?
                AND r.profile_version = ?
          )
        ORDER BY j.updated_at DESC, j.id DESC
        LIMIT ?
        """,
        (JobStage.ENRICHED, prompt_version, profile_version, limit),
    ).fetchall()
    return [_row_to_ranking_input(row) for row in rows]


def save_job_rankings(
    connection: sqlite3.Connection,
    rankings: list[LinkedInJobRankingResult],
    *,
    model_name: str,
    prompt_version: str,
    profile_version: str,
) -> dict[str, int]:
    summary = {
        "rankings_received": len(rankings),
        "rankings_inserted": 0,
        "jobs_missing": 0,
        "jobs_marked_not_applicable": 0,
        "apply_focus_count": 0,
        "apply_auto_count": 0,
        "low_priority_count": 0,
    }
    now = now_iso()

    with connection:
        for ranking in rankings:
            job_row = connection.execute(
                "SELECT id, stage FROM jobs WHERE linkedin_job_id = ?",
                (ranking.linkedin_job_id,),
            ).fetchone()
            if job_row is None:
                summary["jobs_missing"] += 1
                continue
            if ranking.not_applicable_reason:
                validate_stage_transition(job_row["stage"], JobStage.NOT_APPLICABLE)
                update_job_by_linkedin_job_id(
                    connection,
                    assignments_sql="""
                        stage = ?,
                        stage_reason = ?,
                        stage_updated_at = ?,
                        updated_at = ?
                    """,
                    values=(
                        JobStage.NOT_APPLICABLE,
                        ranking.not_applicable_reason,
                        now,
                        now,
                    ),
                    linkedin_job_id=ranking.linkedin_job_id,
                )
                summary["jobs_marked_not_applicable"] += 1
            else:
                validate_stage_transition(job_row["stage"], JobStage.RANKED)
                update_job_by_linkedin_job_id(
                    connection,
                    assignments_sql="""
                        stage = ?,
                        stage_reason = NULL,
                        stage_updated_at = ?,
                        updated_at = ?
                    """,
                    values=(
                        JobStage.RANKED,
                        now,
                        now,
                    ),
                    linkedin_job_id=ranking.linkedin_job_id,
                )
            connection.execute(
                """
                INSERT OR REPLACE INTO job_rankings (
                    job_id,
                    linkedin_job_id,
                    model_name,
                    prompt_version,
                    profile_version,
                    role_match_label,
                    role_match_reason,
                    level_match_label,
                    level_match_reason,
                    preference_match_label,
                    preference_match_reason,
                    recommendation,
                    summary,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(job_row["id"]),
                    ranking.linkedin_job_id,
                    model_name,
                    prompt_version,
                    profile_version,
                    ranking.role_match.label,
                    ranking.role_match.reason,
                    ranking.level_match.label,
                    ranking.level_match.reason,
                    ranking.preference_match.label,
                    ranking.preference_match.reason,
                    ranking.recommendation,
                    ranking.summary,
                    now,
                ),
            )
            summary["rankings_inserted"] += 1
            if ranking.recommendation == "apply_focus":
                summary["apply_focus_count"] += 1
            elif ranking.recommendation == "apply_auto":
                summary["apply_auto_count"] += 1
            else:
                summary["low_priority_count"] += 1

    return summary
