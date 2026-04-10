from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.email import LinkedInApplicationConfirmation, LinkedInRawEmailMessage
from app.models.job import LinkedInJobCard


class LinkedInConnectionResult(BaseModel):
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    success: bool
    cdp_url: str
    test_url: str
    expected_domain_contains: str
    current_url: str | None = None
    page_title: str | None = None
    browser_connected: bool = False
    linkedin_accessible: bool = False
    not_on_login_signup_page: bool = False
    error: str | None = None


class LinkedInEmailResultBase(BaseModel):
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    success: bool
    provider: Literal["imap"] = "imap"
    host: str
    port: int
    mailbox: str
    username: str
    sender: str
    lookback_days: int
    max_messages: int
    authenticated: bool = False
    mailbox_selected: bool = False
    error: str | None = None


class LinkedInEmailConnectionResult(LinkedInEmailResultBase):
    pass


class LinkedInEmailFetchResult(LinkedInEmailResultBase):
    matched_message_count: int = 0
    messages: list[LinkedInRawEmailMessage] = Field(default_factory=list)
    job_cards: list[LinkedInJobCard] = Field(default_factory=list)


class LinkedInApplicationConfirmationFetchResult(LinkedInEmailResultBase):
    matched_message_count: int = 0
    messages: list[LinkedInRawEmailMessage] = Field(default_factory=list)
    confirmations: list[LinkedInApplicationConfirmation] = Field(default_factory=list)


class LinkedInCollectionResult(BaseModel):
    searched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_type: str
    source_url: str
    cards_requested_total: int
    unique_cards_total: int = 0
    title_filtered_total: int = 0
    title_filtered_titles: list[str] = Field(default_factory=list)
    duplicates_skipped_total: int = 0
    offsets_visited: list[int] = Field(default_factory=list)
    stopped_reason: str
    chunks: list[dict[str, object]] = Field(default_factory=list)
    job_cards: list[LinkedInJobCard] = Field(default_factory=list)
