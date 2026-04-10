from __future__ import annotations

import sqlite3

from app.models import LinkedInTitleTriageCandidate, LinkedInTitleTriageDecision
from app.services.storage._shared import load_job_rows_by_stage, now_iso
from app.services.storage.stages import JobStage, validate_stage_transition


def load_discovered_jobs(
    connection: sqlite3.Connection,
    limit: int,
) -> list[LinkedInTitleTriageCandidate]:
    rows = load_job_rows_by_stage(
        connection,
        stage=JobStage.DISCOVERED,
        select_columns="id, linkedin_job_id, title, company, location_text, work_mode",
        limit=limit,
    )
    return [
        LinkedInTitleTriageCandidate(
            job_id=int(row["id"]),
            linkedin_job_id=row["linkedin_job_id"],
            title=row["title"],
            company=row["company"],
            location_text=row["location_text"],
            work_mode=row["work_mode"],
        )
        for row in rows
    ]


def save_title_triage_results(
    connection: sqlite3.Connection,
    decisions: list[LinkedInTitleTriageDecision],
    model_name: str,
) -> dict[str, int]:
    summary = {
        "decisions_received": len(decisions),
        "jobs_updated": 0,
        "jobs_missing": 0,
        "keep_count": 0,
        "discard_count": 0,
    }
    now = now_iso()

    with connection:
        for decision in decisions:
            to_stage = JobStage.TRIAGED if decision.decision == "keep" else JobStage.NOT_APPLICABLE
            current_row = connection.execute(
                "SELECT stage FROM jobs WHERE linkedin_job_id = ?",
                (decision.linkedin_job_id,),
            ).fetchone()
            if current_row is None:
                summary["jobs_missing"] += 1
                continue
            validate_stage_transition(current_row["stage"], to_stage)
            cursor = connection.execute(
                """
                UPDATE jobs
                SET
                    stage = ?,
                    stage_reason = ?,
                    stage_updated_at = ?,
                    title_triage_model = ?,
                    updated_at = ?
                WHERE linkedin_job_id = ?
                """,
                (
                    to_stage,
                    None if decision.decision == "keep" else decision.reason,
                    now,
                    model_name,
                    now,
                    decision.linkedin_job_id,
                ),
            )
            if cursor.rowcount == 0:
                summary["jobs_missing"] += 1
                continue
            summary["jobs_updated"] += 1
            if decision.decision == "keep":
                summary["keep_count"] += 1
            else:
                summary["discard_count"] += 1

    return summary
