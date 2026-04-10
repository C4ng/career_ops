from __future__ import annotations

import sqlite3

from app.services.storage._shared import now_iso


class JobStage:
    """Valid values for the ``jobs.stage`` column."""

    DISCOVERED = "discovered"
    TRIAGED = "triaged"
    DETAILED = "detailed"
    ENRICHED = "enriched"
    RANKED = "ranked"
    APPLIED = "applied"
    NOT_APPLICABLE = "not_applicable"


ALL_STAGES: frozenset[str] = frozenset({
    JobStage.DISCOVERED,
    JobStage.TRIAGED,
    JobStage.DETAILED,
    JobStage.ENRICHED,
    JobStage.RANKED,
    JobStage.APPLIED,
    JobStage.NOT_APPLICABLE,
})

# Maps each stage to the stages it may advance to.
# Terminal stages (APPLIED, NOT_APPLICABLE) map to empty sets.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    JobStage.DISCOVERED:     frozenset({JobStage.TRIAGED, JobStage.NOT_APPLICABLE}),
    JobStage.TRIAGED:        frozenset({JobStage.DETAILED, JobStage.NOT_APPLICABLE}),
    JobStage.DETAILED:       frozenset({JobStage.ENRICHED, JobStage.NOT_APPLICABLE}),
    JobStage.ENRICHED:       frozenset({JobStage.RANKED, JobStage.APPLIED, JobStage.NOT_APPLICABLE}),
    JobStage.RANKED:         frozenset({JobStage.APPLIED, JobStage.NOT_APPLICABLE}),
    JobStage.APPLIED:        frozenset(),
    JobStage.NOT_APPLICABLE: frozenset(),
}


class InvalidStageTransitionError(ValueError):
    """Raised when a job stage transition is not permitted."""


def validate_stage_transition(from_stage: str, to_stage: str) -> None:
    """Raise ``InvalidStageTransitionError`` if *from_stage* → *to_stage* is not allowed."""
    allowed = ALLOWED_TRANSITIONS.get(from_stage)
    if allowed is None:
        raise InvalidStageTransitionError(f"Unknown job stage: {from_stage!r}")
    if to_stage not in allowed:
        terminal = " (terminal)" if not allowed else ""
        raise InvalidStageTransitionError(
            f"Invalid job stage transition: {from_stage!r} → {to_stage!r}. "
            f"Allowed from {from_stage!r}: {sorted(allowed) or 'none'}{terminal}"
        )


def advance_job_stage(
    connection: sqlite3.Connection,
    linkedin_job_id: str,
    to_stage: str,
    *,
    reason: str | None = None,
) -> bool:
    """Advance *linkedin_job_id* to *to_stage*, enforcing allowed transitions.

    Returns ``True`` if the job was found and updated, ``False`` if not found.
    Raises ``InvalidStageTransitionError`` for illegal transitions.
    """
    row = connection.execute(
        "SELECT stage FROM jobs WHERE linkedin_job_id = ?",
        (linkedin_job_id,),
    ).fetchone()
    if row is None:
        return False
    validate_stage_transition(row["stage"], to_stage)
    now = now_iso()
    connection.execute(
        """
        UPDATE jobs
        SET stage = ?, stage_reason = ?, stage_updated_at = ?, updated_at = ?
        WHERE linkedin_job_id = ?
        """,
        (to_stage, reason, now, now, linkedin_job_id),
    )
    return True
