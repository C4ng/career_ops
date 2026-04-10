from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LinkedInTitleTriageCandidate(BaseModel):
    job_id: int
    linkedin_job_id: str
    title: str
    company: str
    location_text: str | None = None
    work_mode: str | None = None


class LinkedInTitleTriageDecision(BaseModel):
    linkedin_job_id: str
    decision: Literal["keep", "discard"]
    reason: str


class LinkedInRankingLabeledReason(BaseModel):
    label: str
    reason: str


class LinkedInJobRankingResult(BaseModel):
    linkedin_job_id: str
    role_match: LinkedInRankingLabeledReason
    level_match: LinkedInRankingLabeledReason
    preference_match: LinkedInRankingLabeledReason
    not_applicable_reason: str | None = None
    recommendation: Literal["apply_focus", "apply_auto", "low_priority"]
    summary: str
