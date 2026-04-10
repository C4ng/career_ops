from __future__ import annotations

from pydantic import BaseModel


class LinkedInRawEmailMessage(BaseModel):
    sequence_id: str
    message_id: str | None = None
    subject: str | None = None
    from_address: str | None = None
    received_at: str | None = None
    text_body: str | None = None
    html_body: str | None = None


class LinkedInApplicationConfirmation(BaseModel):
    sequence_id: str
    message_id: str | None = None
    subject: str | None = None
    from_address: str | None = None
    received_at: str | None = None
    linkedin_job_id: str | None = None
    job_url: str | None = None
    company: str | None = None
    title: str | None = None
    confirmation_text: str | None = None
