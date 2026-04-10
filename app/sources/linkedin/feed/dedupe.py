from __future__ import annotations

from app.models import LinkedInJobCard


def job_card_dedupe_key(card: LinkedInJobCard) -> str | None:
    if card.linkedin_job_id:
        return f"linkedin_job_id:{card.linkedin_job_id}"
    if card.job_url:
        return f"job_url:{card.job_url}"
    parts = [card.title or "", card.company or "", card.location_text or ""]
    normalized = "|".join(part.strip().lower() for part in parts if part)
    return f"title_company_location:{normalized}" if normalized else None
