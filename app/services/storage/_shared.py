from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from app.models import LinkedInJobCard


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def serialize_to_json_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list) and not value:
        return None
    if isinstance(value, dict) and not value:
        return None
    return json.dumps(value, ensure_ascii=False)


def observed_at_value(job_card: LinkedInJobCard) -> str | None:
    if job_card.observed_at is None:
        return None
    return job_card.observed_at.isoformat()


def load_job_rows_by_stage(
    connection: sqlite3.Connection,
    *,
    stage: str,
    select_columns: str,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    sql = f"""
        SELECT {select_columns}
        FROM jobs
        WHERE stage = ?
        ORDER BY updated_at DESC, id DESC
    """
    params: list[object] = [stage]
    if limit is not None:
        sql += "\nLIMIT ?"
        params.append(limit)
    return connection.execute(sql, tuple(params)).fetchall()


def update_job_by_linkedin_job_id(
    connection: sqlite3.Connection,
    *,
    assignments_sql: str,
    values: tuple[object, ...],
    linkedin_job_id: str,
) -> int:
    """Execute ``UPDATE jobs SET {assignments_sql} WHERE linkedin_job_id = ?``.

    ``assignments_sql`` must be a compile-time literal string (never user-supplied).
    Values are passed as parameterised ``?`` placeholders — no f-string interpolation
    is allowed in the assignments body.
    """
    if "{" in assignments_sql or "}" in assignments_sql:
        raise ValueError(
            "assignments_sql must not contain brace characters. "
            "Pass dynamic values via the 'values' tuple, not by string formatting."
        )
    cursor = connection.execute(
        f"""
        UPDATE jobs
        SET
            {assignments_sql}
        WHERE linkedin_job_id = ?
        """,
        (*values, linkedin_job_id),
    )
    return cursor.rowcount


def requirements_has_content(requirements: dict[str, object] | None) -> bool:
    if not requirements:
        return False
    return any(requirements.get(key) for key in requirements)
