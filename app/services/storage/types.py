"""TypedDicts for storage layer return values.

Replacing bare ``dict[str, object]`` with these types makes call-site code
readable, enables static analysis, and documents the contract of each function.
"""
from __future__ import annotations

from typing import TypedDict


class RankedJobRow(TypedDict):
    job_id: int
    linkedin_job_id: str
    job_url: str
    apply_link: str | None
    title: str
    company: str
    location_text: str | None
    work_mode: str | None
    salary_text: str | None
    employment_type: str | None
    application_status_text: str | None
    easy_apply: bool
    recommendation: str


class ApplicationRow(TypedDict):
    application_id: int
    job_id: int
    linkedin_job_id: str
    application_type: str
    status: str
    review_step_name: str | None
    last_seen_url: str | None
    last_screenshot_path: str | None
    submitted_at: str | None


class SubmittedPendingApplicationRow(TypedDict):
    application_id: int
    job_id: int
    linkedin_job_id: str
    application_type: str
    status: str
    last_seen_url: str | None
    submitted_at: str | None
    job_url: str
    title: str
    company: str


class ApplicationQuestionRow(TypedDict):
    id: int
    step_index: int
    step_name: str | None
    question_key: str
    prompt_text: str
    input_type: str
    required: bool
    options: list[str]
    current_value: str | None
    field_name: str | None
    field_id: str | None
    answer_source: str | None
    answer_value: str | None
    confidence: str | None
    requires_user_input: bool
    reason: str | None
    fill_status: str


class ConfirmationResult(TypedDict):
    linkedin_job_id: str
    job_found: bool
    application_created: bool
    application_updated: bool
    job_updated: bool
