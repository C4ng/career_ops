from __future__ import annotations

import pytest

from app.services.storage.db import connect_sqlite, initialize_schema
from app.services.storage.stages import (
    ALLOWED_TRANSITIONS,
    ALL_STAGES,
    JobStage,
    InvalidStageTransitionError,
    advance_job_stage,
    validate_stage_transition,
)


# --- validate_stage_transition ---


def test_valid_transitions_do_not_raise() -> None:
    valid_pairs = [
        (JobStage.DISCOVERED, JobStage.TRIAGED),
        (JobStage.DISCOVERED, JobStage.NOT_APPLICABLE),
        (JobStage.TRIAGED, JobStage.DETAILED),
        (JobStage.TRIAGED, JobStage.NOT_APPLICABLE),
        (JobStage.DETAILED, JobStage.ENRICHED),
        (JobStage.DETAILED, JobStage.NOT_APPLICABLE),
        (JobStage.ENRICHED, JobStage.RANKED),
        (JobStage.ENRICHED, JobStage.APPLIED),
        (JobStage.ENRICHED, JobStage.NOT_APPLICABLE),
        (JobStage.RANKED, JobStage.APPLIED),
        (JobStage.RANKED, JobStage.NOT_APPLICABLE),
    ]
    for from_stage, to_stage in valid_pairs:
        validate_stage_transition(from_stage, to_stage)  # must not raise


def test_invalid_transition_raises() -> None:
    with pytest.raises(InvalidStageTransitionError, match="triaged.*enriched"):
        validate_stage_transition(JobStage.TRIAGED, JobStage.ENRICHED)


def test_terminal_stage_applied_raises_on_any_transition() -> None:
    for to_stage in ALL_STAGES - {JobStage.APPLIED}:
        with pytest.raises(InvalidStageTransitionError):
            validate_stage_transition(JobStage.APPLIED, to_stage)


def test_terminal_stage_not_applicable_raises_on_any_transition() -> None:
    for to_stage in ALL_STAGES - {JobStage.NOT_APPLICABLE}:
        with pytest.raises(InvalidStageTransitionError):
            validate_stage_transition(JobStage.NOT_APPLICABLE, to_stage)


def test_unknown_from_stage_raises() -> None:
    with pytest.raises(InvalidStageTransitionError, match="Unknown job stage"):
        validate_stage_transition("ghost_stage", JobStage.TRIAGED)


def test_skipping_stages_raises() -> None:
    """Skipping directly from discovered to enriched must be rejected."""
    with pytest.raises(InvalidStageTransitionError):
        validate_stage_transition(JobStage.DISCOVERED, JobStage.ENRICHED)


def test_all_stages_present_in_allowed_transitions() -> None:
    """Every stage must have an entry in ALLOWED_TRANSITIONS."""
    assert set(ALLOWED_TRANSITIONS.keys()) == ALL_STAGES


# --- advance_job_stage ---


def _seed_job(connection, linkedin_job_id: str, stage: str = JobStage.DISCOVERED) -> None:
    connection.execute(
        """
        INSERT INTO jobs (
            linkedin_job_id, job_url, title, company, easy_apply,
            stage, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'now', 'now')
        """,
        (linkedin_job_id, "https://example.com/", "AI Engineer", "Acme", 1, stage),
    )
    connection.commit()


def test_advance_job_stage_updates_stage(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "test.sqlite3")
    try:
        initialize_schema(connection)
        _seed_job(connection, "job1")
        with connection:
            found = advance_job_stage(connection, "job1", JobStage.TRIAGED)
        row = connection.execute(
            "SELECT stage FROM jobs WHERE linkedin_job_id = 'job1'"
        ).fetchone()
    finally:
        connection.close()

    assert found is True
    assert row["stage"] == JobStage.TRIAGED


def test_advance_job_stage_sets_reason(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "test.sqlite3")
    try:
        initialize_schema(connection)
        _seed_job(connection, "job1")
        with connection:
            advance_job_stage(connection, "job1", JobStage.NOT_APPLICABLE, reason="no AI cue")
        row = connection.execute(
            "SELECT stage, stage_reason FROM jobs WHERE linkedin_job_id = 'job1'"
        ).fetchone()
    finally:
        connection.close()

    assert row["stage"] == JobStage.NOT_APPLICABLE
    assert row["stage_reason"] == "no AI cue"


def test_advance_job_stage_returns_false_for_missing_job(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "test.sqlite3")
    try:
        initialize_schema(connection)
        with connection:
            found = advance_job_stage(connection, "nonexistent", JobStage.TRIAGED)
    finally:
        connection.close()

    assert found is False


def test_advance_job_stage_raises_for_invalid_transition(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "test.sqlite3")
    try:
        initialize_schema(connection)
        _seed_job(connection, "job1", stage=JobStage.ENRICHED)
        with pytest.raises(InvalidStageTransitionError):
            with connection:
                advance_job_stage(connection, "job1", JobStage.DISCOVERED)
        # Stage must be unchanged
        row = connection.execute(
            "SELECT stage FROM jobs WHERE linkedin_job_id = 'job1'"
        ).fetchone()
    finally:
        connection.close()

    assert row["stage"] == JobStage.ENRICHED


def test_advance_job_stage_raises_from_terminal_applied(tmp_path) -> None:
    connection = connect_sqlite(tmp_path / "test.sqlite3")
    try:
        initialize_schema(connection)
        _seed_job(connection, "job1", stage=JobStage.APPLIED)
        with pytest.raises(InvalidStageTransitionError, match="terminal"):
            with connection:
                advance_job_stage(connection, "job1", JobStage.RANKED)
    finally:
        connection.close()
