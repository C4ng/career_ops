from __future__ import annotations

from app.application.confirmation import (
    page_text_contains_job_page_applied_signal,
    page_text_contains_my_jobs_applied_signal,
)


def test_page_text_contains_my_jobs_applied_signal_detects_applied_listing() -> None:
    body_text = """
    My Jobs
    Saved
    In Progress
    Applied
    Archived
    Founding AI / Data Engineer (Semantic Systems)
    MachAI
    Applied 1h ago
    """

    assert page_text_contains_my_jobs_applied_signal(
        body_text,
        title="Founding AI / Data Engineer (Semantic Systems)",
        company="MachAI",
    ) is True


def test_page_text_contains_job_page_applied_signal_detects_job_page_status_block() -> None:
    body_text = """
    BrandActive
    AI Solutions Developer
    Application status
    Application submitted
    now
    View resume
    """

    assert page_text_contains_job_page_applied_signal(
        body_text,
        title="AI Solutions Developer",
        company="BrandActive",
    ) is True
