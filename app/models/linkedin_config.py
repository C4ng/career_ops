from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# LinkedIn connection & source configs
# ---------------------------------------------------------------------------

DEFAULT_CDP_URL = "http://127.0.0.1:9222"


class LinkedInConnectionConfig(BaseModel):
    cdp_url: str = DEFAULT_CDP_URL
    test_url: str = "https://www.linkedin.com/feed/"
    expected_domain_contains: str = "linkedin.com"


class LinkedInKeywordSearchSource(BaseModel):
    keywords: str
    location: str
    posted_window: str = "past_week"
    experience_levels: list[str] = Field(default_factory=list)
    start: int = 0


class LinkedInRecommendedFeedSource(BaseModel):
    recommended_url: str


class LinkedInSourceConfig(BaseModel):
    source_type: list[Literal["keyword_search", "recommended_feed"]] = Field(default_factory=list)
    cdp_url: str = DEFAULT_CDP_URL
    keyword_search_page_step: int = 25
    recommended_feed_page_step: int = 24
    title_exclude_contains: list[str] = Field(default_factory=list)
    collect_limit: int = 10
    max_offsets: int = 10
    keyword_search: LinkedInKeywordSearchSource | None = None
    recommended_feed: LinkedInRecommendedFeedSource | None = None

    @model_validator(mode="after")
    def validate_selected_source(self) -> "LinkedInSourceConfig":
        if not self.source_type:
            raise ValueError("source_type must contain at least one source")
        deduped: list[str] = []
        for source in self.source_type:
            if source not in deduped:
                deduped.append(source)
        self.source_type = deduped
        if "keyword_search" in self.source_type and self.keyword_search is None:
            raise ValueError("keyword_search config is required when source_type includes keyword_search")
        if "recommended_feed" in self.source_type and self.recommended_feed is None:
            raise ValueError("recommended_feed config is required when source_type includes recommended_feed")
        return self


# ---------------------------------------------------------------------------
# LinkedIn email config
# ---------------------------------------------------------------------------


class LinkedInEmailConfig(BaseModel):
    provider: Literal["imap"] = "imap"
    host: str
    port: int = 993
    mailbox: str = "INBOX"
    username: str
    password_env: str
    sender: str
    lookback_days: int = 7
    max_messages: int = 30
    title_exclude_contains: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LinkedIn title triage configs
# ---------------------------------------------------------------------------


class LinkedInTitleTriageRoleIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied_ai_engineering: str | None = None
    research_and_modeling: str | None = None


class LinkedInTitleTriageExamples(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keep: list[str] = Field(default_factory=list)
    discard: list[str] = Field(default_factory=list)


class LinkedInTitleTriageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    role_intent: LinkedInTitleTriageRoleIntent | None = None
    wanted_roles: list[str] = Field(default_factory=list)
    wanted_technical_cues: list[str] = Field(default_factory=list)
    decision_rules: list[str] = Field(default_factory=list)
    strong_keep_patterns: list[str] = Field(default_factory=list)
    discard_patterns: list[str] = Field(default_factory=list)
    location_policy: list[str] = Field(default_factory=list)
    important_examples: LinkedInTitleTriageExamples | None = None


# ---------------------------------------------------------------------------
# LinkedIn ranking configs
# ---------------------------------------------------------------------------


class LinkedInRankingTargetConfig(BaseModel):
    preferred_roles: list[str] = Field(default_factory=list)
    acceptable_roles: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=list)
    acceptable_domains: list[str] = Field(default_factory=list)
    preferred_work_styles: list[str] = Field(default_factory=list)
    acceptable_work_styles: list[str] = Field(default_factory=list)


class LinkedInRankingSeniorityPreference(BaseModel):
    preferred: list[str] = Field(default_factory=list)
    acceptable: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class LinkedInRankingCandidateProfile(BaseModel):
    seniority_preference: LinkedInRankingSeniorityPreference
    strengths: list[str] = Field(default_factory=list)
    tech_familiarity: list[str] = Field(default_factory=list)
    weaker_areas: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class LinkedInRankingPreferenceBucket(BaseModel):
    work_mode: list[str] = Field(default_factory=list)
    employment_type: list[str] = Field(default_factory=list)


class LinkedInRankingPreferences(BaseModel):
    preferred: LinkedInRankingPreferenceBucket
    acceptable: LinkedInRankingPreferenceBucket
    lower_preference_signals: list[str] = Field(default_factory=list)


class LinkedInRankingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_version: str = "v1"
    target: LinkedInRankingTargetConfig
    candidate_profile: LinkedInRankingCandidateProfile
    preferences: LinkedInRankingPreferences
