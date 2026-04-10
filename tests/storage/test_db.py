from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services.storage.db import SQLiteConfig, _MIGRATIONS, apply_pending_migrations, connect_sqlite, initialize_schema, resolve_db_path


def _table_columns(connection: sqlite3.Connection, table_name: str) -> dict[str, dict[str, object]]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {
        row["name"]: {
            "type": row["type"],
            "notnull": bool(row["notnull"]),
            "pk": bool(row["pk"]),
        }
        for row in rows
    }


def test_resolve_db_path_uses_root_for_relative_path(tmp_path: Path) -> None:
    config = SQLiteConfig(db_path="data/test.sqlite3")

    resolved = resolve_db_path(tmp_path, config)

    assert resolved == tmp_path / "data" / "test.sqlite3"


def test_initialize_schema_creates_jobs_job_observations_job_rankings_and_application_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "job_finding.sqlite3"
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)

        jobs_columns = _table_columns(connection, "jobs")
        observations_columns = _table_columns(connection, "job_observations")
        rankings_columns = _table_columns(connection, "job_rankings")
        applications_columns = _table_columns(connection, "job_applications")
        application_questions_columns = _table_columns(connection, "job_application_questions")
        processed_confirmation_columns = _table_columns(connection, "processed_linkedin_confirmation_emails")
    finally:
        connection.close()

    assert jobs_columns["id"]["pk"] is True
    assert jobs_columns["linkedin_job_id"]["notnull"] is True
    assert jobs_columns["job_url"]["notnull"] is True
    assert jobs_columns["title"]["notnull"] is True
    assert jobs_columns["company"]["notnull"] is True
    assert jobs_columns["easy_apply"]["notnull"] is True
    assert "job_description" in jobs_columns
    assert "company_intro" in jobs_columns
    assert "role_scope" in jobs_columns
    assert "requirements" in jobs_columns
    assert "benefits" in jobs_columns
    assert "application_details" in jobs_columns
    assert "apply_link" in jobs_columns
    assert "observed_posted_text" in jobs_columns
    assert "employment_type" in jobs_columns
    assert "applicant_count_text" in jobs_columns
    assert "application_status_text" in jobs_columns
    assert "applied_at" in jobs_columns
    assert "stage" in jobs_columns
    assert "stage_reason" in jobs_columns
    assert "stage_updated_at" in jobs_columns
    assert "title_triage_model" in jobs_columns

    assert observations_columns["id"]["pk"] is True
    assert observations_columns["job_id"]["notnull"] is True
    assert observations_columns["linkedin_job_id"]["notnull"] is True
    assert observations_columns["source_type"]["notnull"] is True
    assert observations_columns["title"]["notnull"] is True
    assert observations_columns["company"]["notnull"] is True
    assert observations_columns["easy_apply"]["notnull"] is True
    assert rankings_columns["job_id"]["notnull"] is True
    assert rankings_columns["linkedin_job_id"]["notnull"] is True
    assert rankings_columns["role_match_label"]["notnull"] is True
    assert rankings_columns["level_match_label"]["notnull"] is True
    assert rankings_columns["preference_match_label"]["notnull"] is True
    assert rankings_columns["recommendation"]["notnull"] is True
    assert applications_columns["job_id"]["notnull"] is True
    assert applications_columns["linkedin_job_id"]["notnull"] is True
    assert applications_columns["application_type"]["notnull"] is True
    assert applications_columns["status"]["notnull"] is True
    assert "submitted_at" in applications_columns
    assert processed_confirmation_columns["dedupe_key"]["notnull"] is True
    assert processed_confirmation_columns["processing_result"]["notnull"] is True
    assert application_questions_columns["application_id"]["notnull"] is True
    assert application_questions_columns["question_key"]["notnull"] is True
    assert application_questions_columns["prompt_text"]["notnull"] is True
    assert application_questions_columns["input_type"]["notnull"] is True
    assert "field_name" in application_questions_columns
    assert "field_id" in application_questions_columns
    assert application_questions_columns["fill_status"]["notnull"] is True

    indexes_connection = connect_sqlite(db_path)
    try:
        index_names = {row["name"] for row in indexes_connection.execute("PRAGMA index_list(jobs)").fetchall()}
        observation_index_names = {
            row["name"] for row in indexes_connection.execute("PRAGMA index_list(job_observations)").fetchall()
        }
        ranking_index_names = {
            row["name"] for row in indexes_connection.execute("PRAGMA index_list(job_rankings)").fetchall()
        }
        application_index_names = {
            row["name"] for row in indexes_connection.execute("PRAGMA index_list(job_applications)").fetchall()
        }
        application_question_index_names = {
            row["name"] for row in indexes_connection.execute("PRAGMA index_list(job_application_questions)").fetchall()
        }
        processed_confirmation_index_names = {
            row["name"]
            for row in indexes_connection.execute(
                "PRAGMA index_list(processed_linkedin_confirmation_emails)"
            ).fetchall()
        }
    finally:
        indexes_connection.close()

    assert "idx_jobs_linkedin_job_id" in index_names
    assert "idx_job_observations_job_id" in observation_index_names
    assert "idx_job_observations_linkedin_job_id" in observation_index_names
    assert "idx_job_rankings_job_id" in ranking_index_names
    assert "idx_job_rankings_linkedin_job_id" in ranking_index_names
    assert "idx_job_applications_job_id" in application_index_names
    assert "idx_job_applications_linkedin_job_id" in application_index_names
    assert "idx_job_application_questions_application_id" in application_question_index_names
    assert "idx_job_application_questions_linkedin_job_id" in application_question_index_names
    assert "idx_processed_confirmation_emails_dedupe_key" in processed_confirmation_index_names
    assert "idx_processed_confirmation_emails_message_id" in processed_confirmation_index_names


def test_connect_sqlite_enables_named_row_access(tmp_path: Path) -> None:
    """connect_sqlite must set row_factory=sqlite3.Row so columns are accessible by name."""
    db_path = tmp_path / "data" / "test.sqlite3"
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        connection.execute(
            """
            INSERT INTO jobs (linkedin_job_id, job_url, title, company, easy_apply, created_at, updated_at)
            VALUES ('abc123', 'https://example.com/', 'AI Engineer', 'Example', 1, 'now', 'now')
            """
        )
        connection.commit()
        row = connection.execute(
            "SELECT linkedin_job_id, title, easy_apply FROM jobs WHERE linkedin_job_id = 'abc123'"
        ).fetchone()
    finally:
        connection.close()

    assert isinstance(row, sqlite3.Row)
    # Named access works
    assert row["linkedin_job_id"] == "abc123"
    assert row["title"] == "AI Engineer"
    assert row["easy_apply"] == 1
    # Positional access still works (backwards compatible)
    assert row[0] == "abc123"
    assert row[1] == "AI Engineer"
    assert row[2] == 1


def test_connect_sqlite_named_access_is_order_independent(tmp_path: Path) -> None:
    """Changing SELECT column order must not break named access."""
    db_path = tmp_path / "data" / "test.sqlite3"
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        connection.execute(
            """
            INSERT INTO jobs (linkedin_job_id, job_url, title, company, easy_apply, created_at, updated_at)
            VALUES ('xyz', 'https://example.com/', 'ML Engineer', 'Corp', 0, 'now', 'now')
            """
        )
        connection.commit()
        # Deliberately reversed order vs. how columns appear in the schema
        row = connection.execute(
            "SELECT easy_apply, company, title, linkedin_job_id FROM jobs WHERE linkedin_job_id = 'xyz'"
        ).fetchone()
    finally:
        connection.close()

    # Named access is unaffected by SELECT order
    assert row["linkedin_job_id"] == "xyz"
    assert row["title"] == "ML Engineer"
    assert row["company"] == "Corp"
    assert row["easy_apply"] == 0


# --- schema_migrations (Issue #5) ---


def test_initialize_schema_records_all_migrations_in_schema_migrations_table(tmp_path: Path) -> None:
    """After initialize_schema, every migration must be recorded with an applied_at timestamp."""
    db_path = tmp_path / "data" / "test.sqlite3"
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        rows = connection.execute(
            "SELECT migration_id, applied_at FROM schema_migrations ORDER BY id"
        ).fetchall()
    finally:
        connection.close()

    recorded_ids = [row["migration_id"] for row in rows]
    expected_ids = [m[0] for m in _MIGRATIONS]
    assert recorded_ids == expected_ids
    # Every migration must have a non-empty applied_at
    for row in rows:
        assert row["applied_at"], f"migration {row['migration_id']} has no applied_at"


def test_apply_pending_migrations_is_idempotent(tmp_path: Path) -> None:
    """Running apply_pending_migrations twice must not re-apply already recorded migrations."""
    db_path = tmp_path / "data" / "test.sqlite3"
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        count_after_first = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]

        # Second run — nothing new should be applied
        newly_applied = apply_pending_migrations(connection)
        count_after_second = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
    finally:
        connection.close()

    assert newly_applied == []
    assert count_after_first == count_after_second


def test_apply_pending_migrations_only_runs_new_migrations(tmp_path: Path) -> None:
    """Simulate an old database missing later migrations — only the missing ones should run."""
    db_path = tmp_path / "data" / "test.sqlite3"
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)

        # Manually remove the last two migration records to simulate them never having run
        all_ids = [m[0] for m in _MIGRATIONS]
        if len(all_ids) < 2:
            return  # Nothing to test with fewer than 2 migrations

        ids_to_remove = all_ids[-2:]
        for mid in ids_to_remove:
            connection.execute(
                "DELETE FROM schema_migrations WHERE migration_id = ?", (mid,)
            )
        connection.commit()

        # apply_pending_migrations should re-apply only the removed ones
        newly_applied = apply_pending_migrations(connection)
        connection.commit()

        final_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
    finally:
        connection.close()

    assert set(newly_applied) == set(ids_to_remove)
    assert final_count == len(all_ids)


def test_schema_migrations_table_is_created_by_initialize_schema(tmp_path: Path) -> None:
    """The schema_migrations table must exist after initialize_schema."""
    db_path = tmp_path / "data" / "test.sqlite3"
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert "schema_migrations" in tables
