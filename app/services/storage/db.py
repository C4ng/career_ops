from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class SQLiteConfig(BaseModel):
    db_path: str = "data/job_finding.sqlite3"


def resolve_db_path(root: Path, config: SQLiteConfig) -> Path:
    raw_path = Path(config.db_path)
    if raw_path.is_absolute():
        return raw_path
    return root / raw_path


def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            linkedin_job_id TEXT NOT NULL UNIQUE,
            job_url TEXT NOT NULL,
            apply_link TEXT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location_text TEXT,
            work_mode TEXT,
            observed_posted_text TEXT,
            salary_text TEXT,
            job_description TEXT,
            company_intro TEXT,
            role_scope TEXT,
            requirements TEXT,
            benefits TEXT,
            application_details TEXT,
            employment_type TEXT,
            applicant_count_text TEXT,
            application_status_text TEXT,
            applied_at TEXT,
            easy_apply INTEGER NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT 'discovered',
            stage_reason TEXT,
            stage_updated_at TEXT,
            title_triage_model TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS job_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            linkedin_job_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            observed_at TEXT,
            job_url TEXT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location_text TEXT,
            work_mode TEXT,
            observed_posted_text TEXT,
            salary_text TEXT,
            easy_apply INTEGER NOT NULL DEFAULT 0,
            badges TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (linkedin_job_id) REFERENCES jobs(linkedin_job_id)
        );

        CREATE TABLE IF NOT EXISTS job_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            linkedin_job_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            profile_version TEXT NOT NULL,
            role_match_label TEXT NOT NULL,
            role_match_reason TEXT NOT NULL,
            level_match_label TEXT NOT NULL,
            level_match_reason TEXT NOT NULL,
            preference_match_label TEXT NOT NULL,
            preference_match_reason TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (linkedin_job_id) REFERENCES jobs(linkedin_job_id),
            UNIQUE (linkedin_job_id, prompt_version, profile_version)
        );

        CREATE TABLE IF NOT EXISTS job_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            linkedin_job_id TEXT NOT NULL,
            application_type TEXT NOT NULL,
            ranking_prompt_version TEXT,
            ranking_profile_version TEXT,
            recommendation TEXT,
            status TEXT NOT NULL,
            pause_reason TEXT,
            last_error TEXT,
            review_step_name TEXT,
            last_seen_url TEXT,
            last_screenshot_path TEXT,
            submitted_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (linkedin_job_id) REFERENCES jobs(linkedin_job_id)
        );

        CREATE TABLE IF NOT EXISTS job_application_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            linkedin_job_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            step_name TEXT,
            question_key TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            input_type TEXT NOT NULL,
            required INTEGER NOT NULL DEFAULT 0,
            options_json TEXT,
            current_value TEXT,
            field_name TEXT,
            field_id TEXT,
            normalized_intent TEXT,
            answer_source TEXT,
            answer_value TEXT,
            confidence TEXT,
            requires_user_input INTEGER NOT NULL DEFAULT 0,
            reason TEXT,
            fill_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (application_id) REFERENCES job_applications(id),
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (linkedin_job_id) REFERENCES jobs(linkedin_job_id)
        );

        CREATE TABLE IF NOT EXISTS processed_linkedin_confirmation_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dedupe_key TEXT NOT NULL UNIQUE,
            message_id TEXT,
            sequence_id TEXT,
            received_at TEXT,
            sender TEXT,
            linkedin_job_id TEXT,
            job_url TEXT,
            company TEXT,
            title TEXT,
            processing_result TEXT NOT NULL,
            application_created INTEGER NOT NULL DEFAULT 0,
            application_updated INTEGER NOT NULL DEFAULT 0,
            job_updated INTEGER NOT NULL DEFAULT 0,
            processed_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_linkedin_job_id
            ON jobs(linkedin_job_id);

        CREATE INDEX IF NOT EXISTS idx_job_observations_job_id
            ON job_observations(job_id);

        CREATE INDEX IF NOT EXISTS idx_job_observations_linkedin_job_id
            ON job_observations(linkedin_job_id);

        CREATE INDEX IF NOT EXISTS idx_job_observations_source_type
            ON job_observations(source_type);

        CREATE INDEX IF NOT EXISTS idx_job_observations_observed_at
            ON job_observations(observed_at);

        CREATE INDEX IF NOT EXISTS idx_job_rankings_job_id
            ON job_rankings(job_id);

        CREATE INDEX IF NOT EXISTS idx_job_rankings_linkedin_job_id
            ON job_rankings(linkedin_job_id);

        CREATE INDEX IF NOT EXISTS idx_job_applications_job_id
            ON job_applications(job_id);

        CREATE INDEX IF NOT EXISTS idx_job_applications_linkedin_job_id
            ON job_applications(linkedin_job_id);

        CREATE INDEX IF NOT EXISTS idx_job_applications_status
            ON job_applications(status);

        CREATE INDEX IF NOT EXISTS idx_job_application_questions_application_id
            ON job_application_questions(application_id);

        CREATE INDEX IF NOT EXISTS idx_job_application_questions_linkedin_job_id
            ON job_application_questions(linkedin_job_id);

        CREATE INDEX IF NOT EXISTS idx_processed_confirmation_emails_dedupe_key
            ON processed_linkedin_confirmation_emails(dedupe_key);

        CREATE INDEX IF NOT EXISTS idx_processed_confirmation_emails_message_id
            ON processed_linkedin_confirmation_emails(message_id);

        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_id TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        );
        """
    )
    apply_pending_migrations(connection)
    connection.commit()


# ---------------------------------------------------------------------------
# Schema migrations
# Each entry is (migration_id, description, migration_fn).
# migration_id must be unique and stable — never rename or remove an entry.
# New migrations go at the end of the list.
# ---------------------------------------------------------------------------

_MIGRATIONS: list[tuple[str, str, Callable[[sqlite3.Connection], None]]] = [
    (
        "0001_add_applied_at_to_jobs",
        "Add applied_at column to jobs for tracking when a job was applied to",
        lambda conn: _add_column_if_not_exists(conn, "jobs", "applied_at", "TEXT"),
    ),
    (
        "0002_add_field_name_to_application_questions",
        "Add field_name column to job_application_questions for form element matching",
        lambda conn: _add_column_if_not_exists(conn, "job_application_questions", "field_name", "TEXT"),
    ),
    (
        "0003_add_field_id_to_application_questions",
        "Add field_id column to job_application_questions for form element matching",
        lambda conn: _add_column_if_not_exists(conn, "job_application_questions", "field_id", "TEXT"),
    ),
    (
        "0004_add_submitted_at_to_job_applications",
        "Add submitted_at column to job_applications for tracking submission time",
        lambda conn: _add_column_if_not_exists(conn, "job_applications", "submitted_at", "TEXT"),
    ),
]


def apply_pending_migrations(connection: sqlite3.Connection) -> list[str]:
    """Run any migrations not yet recorded in schema_migrations. Returns applied IDs."""
    applied_ids = {
        row["migration_id"]
        for row in connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
    }
    now = datetime.now(UTC).isoformat()
    newly_applied: list[str] = []
    for migration_id, _description, migration_fn in _MIGRATIONS:
        if migration_id in applied_ids:
            continue
        migration_fn(connection)
        connection.execute(
            "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            (migration_id, now),
        )
        newly_applied.append(migration_id)
    return newly_applied


def _add_column_if_not_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
