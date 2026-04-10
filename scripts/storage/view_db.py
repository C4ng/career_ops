from __future__ import annotations

import sqlite3

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.settings import ROOT as APP_ROOT, load_sqlite_config
from app.services.storage.db import resolve_db_path


def _truncate(value: object, width: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def _render_table(headers: list[str], rows: list[list[object]], widths: list[int]) -> str:
    def render_row(values: list[object]) -> str:
        return " | ".join(_truncate(value, width).ljust(width) for value, width in zip(values, widths, strict=True))

    separator = "-+-".join("-" * width for width in widths)
    lines = [render_row(headers), separator]
    lines.extend(render_row(row) for row in rows)
    return "\n".join(lines)


def _fetch_one(connection: sqlite3.Connection, query: str) -> object:
    row = connection.execute(query).fetchone()
    return row[0] if row else 0


def view_db() -> str:
    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(APP_ROOT, sqlite_config)
    connection = sqlite3.connect(db_path)
    try:
        total_jobs = _fetch_one(connection, "SELECT COUNT(*) FROM jobs")
        total_observations = _fetch_one(connection, "SELECT COUNT(*) FROM job_observations")
        discovered_jobs = _fetch_one(connection, "SELECT COUNT(*) FROM jobs WHERE stage = 'discovered'")

        source_rows = connection.execute(
            """
            SELECT source_type, COUNT(*) AS count
            FROM job_observations
            GROUP BY source_type
            ORDER BY count DESC, source_type ASC
            """
        ).fetchall()
        triage_rows = connection.execute(
            """
            SELECT stage, COUNT(*) AS count
            FROM jobs
            GROUP BY stage
            ORDER BY count DESC, stage ASC
            """
        ).fetchall()

        recent_jobs = connection.execute(
            """
            SELECT
                id,
                linkedin_job_id,
                title,
                company,
                location_text,
                work_mode,
                easy_apply,
                stage
            FROM jobs
            ORDER BY updated_at DESC, id DESC
            LIMIT 12
            """
        ).fetchall()
        recent_stage_updates = connection.execute(
            """
            SELECT
                linkedin_job_id,
                stage,
                title,
                company,
                stage_reason,
                stage_updated_at,
                title_triage_model
            FROM jobs
            WHERE stage_updated_at IS NOT NULL
            ORDER BY stage_updated_at DESC, id DESC
            LIMIT 15
            """
        ).fetchall()

        recent_observations = connection.execute(
            """
            SELECT id, linkedin_job_id, source_type, observed_at, title, company
            FROM job_observations
            ORDER BY created_at DESC, id DESC
            LIMIT 15
            """
        ).fetchall()
    finally:
        connection.close()

    lines: list[str] = []
    lines.append("DB Summary")
    lines.append(f"db_path: {db_path}")
    lines.append(f"total_jobs: {total_jobs}")
    lines.append(f"total_observations: {total_observations}")
    lines.append(f"discovered_jobs: {discovered_jobs}")
    lines.append("")

    lines.append("Observations By Source")
    if source_rows:
        lines.append(_render_table(
            ["source_type", "count"],
            [[row[0], row[1]] for row in source_rows],
            [24, 8],
        ))
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("Jobs By Stage")
    if triage_rows:
        lines.append(_render_table(
            ["stage", "count"],
            [[row[0], row[1]] for row in triage_rows],
            [16, 8],
        ))
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("Recent Jobs")
    if recent_jobs:
        lines.append(_render_table(
            ["id", "linkedin_job_id", "title", "company", "location", "work_mode", "easy_apply", "stage"],
            [list(row) for row in recent_jobs],
            [4, 12, 30, 18, 18, 10, 10, 10],
        ))
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("Recent Stage Updates")
    if recent_stage_updates:
        lines.append(_render_table(
            ["linkedin_job_id", "stage", "title", "company", "reason", "stage_updated_at", "model"],
            [list(row) for row in recent_stage_updates],
            [12, 16, 28, 16, 28, 20, 14],
        ))
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("Recent Observations")
    if recent_observations:
        lines.append(_render_table(
            ["id", "linkedin_job_id", "source_type", "observed_at", "title", "company"],
            [list(row) for row in recent_observations],
            [4, 12, 20, 20, 34, 18],
        ))
    else:
        lines.append("(none)")
    return "\n".join(lines)


def main() -> None:
    print(view_db())


if __name__ == "__main__":
    main()
