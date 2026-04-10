from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LinkedInJobRequirements(BaseModel):
    summary: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)


class LinkedInJobCard(BaseModel):
    source: str = "linkedin"
    source_type: str
    observed_at: datetime | None = None
    linkedin_job_id: str | None = None
    job_url: str | None = None
    apply_link: str | None = None
    title: str | None = None
    company: str | None = None
    location_text: str | None = None
    work_mode: str | None = None
    observed_posted_text: str | None = None
    salary_text: str | None = None
    job_description: str | None = None
    company_intro: list[str] = Field(default_factory=list)
    role_scope: list[str] = Field(default_factory=list)
    requirements: LinkedInJobRequirements | None = None
    benefits: list[str] = Field(default_factory=list)
    application_details: list[str] = Field(default_factory=list)
    employment_type: str | None = None
    applicant_count_text: str | None = None
    application_status_text: str | None = None
    easy_apply: bool = False
    badges: list[str] = Field(default_factory=list)
    raw_card_text: str | None = None


class LinkedInRawCard(BaseModel):
    index: int
    title_text: str | None = None
    company_text: str | None = None
    location_text: str | None = None
    badge_texts: list[str] = Field(default_factory=list)
    href: str | None = None
    current_job_id_guess: str | None = None
    card_text: str | None = None
    card_html: str | None = None
