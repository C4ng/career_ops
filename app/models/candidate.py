from __future__ import annotations

from pydantic import BaseModel, Field


class LinkedInCandidateContact(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    phone_country_label: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    postal_code: str | None = None


class LinkedInCandidateLinks(BaseModel):
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    website_url: str | None = None


class LinkedInCandidateWorkAuthorization(BaseModel):
    work_country: str | None = None
    legally_authorized: bool | None = None
    requires_sponsorship_now: bool | None = None
    requires_sponsorship_future: bool | None = None


class LinkedInCandidateEducation(BaseModel):
    highest_degree: str | None = None
    field_of_study: str | None = None
    school_name: str | None = None
    graduation_date: str | None = None
    currently_enrolled: bool | None = None


class LinkedInCandidateExperience(BaseModel):
    years_total: str | None = None
    current_title: str | None = None
    summary: str | None = None
    highlights: list[str] = Field(default_factory=list)


class LinkedInCandidateDocuments(BaseModel):
    resume_path: str | None = None
    cover_letter_path: str | None = None


class LinkedInCandidateExperienceEntry(BaseModel):
    entry_id: str
    title: str
    organization: str | None = None
    period: str | None = None
    summary: str | None = None
    evidence_points: list[str] = Field(default_factory=list)
    transferable_skills: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class LinkedInCandidateCoverLetterProfile(BaseModel):
    professional_identity: str | None = None
    transition_statement: str | None = None
    motivation_themes: list[str] = Field(default_factory=list)
    tone: str = "concise_professional"


class LinkedInCandidateApplicationPreferences(BaseModel):
    notice_period: str | None = None
    desired_salary: str | None = None
    willing_to_relocate: bool | None = None


class LinkedInCandidateDossier(BaseModel):
    profile_version: str = "v1"
    contact: LinkedInCandidateContact = Field(default_factory=LinkedInCandidateContact)
    links: LinkedInCandidateLinks = Field(default_factory=LinkedInCandidateLinks)
    work_authorization: LinkedInCandidateWorkAuthorization = Field(default_factory=LinkedInCandidateWorkAuthorization)
    education: LinkedInCandidateEducation = Field(default_factory=LinkedInCandidateEducation)
    experience: LinkedInCandidateExperience = Field(default_factory=LinkedInCandidateExperience)
    documents: LinkedInCandidateDocuments = Field(default_factory=LinkedInCandidateDocuments)
    experience_bank: list[LinkedInCandidateExperienceEntry] = Field(default_factory=list)
    cover_letter_profile: LinkedInCandidateCoverLetterProfile = Field(
        default_factory=LinkedInCandidateCoverLetterProfile
    )
    application_preferences: LinkedInCandidateApplicationPreferences = Field(
        default_factory=LinkedInCandidateApplicationPreferences
    )
    strengths: list[str] = Field(default_factory=list)
    tech_familiarity: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    standard_answers: dict[str, object] = Field(default_factory=dict)
