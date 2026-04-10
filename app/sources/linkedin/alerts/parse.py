from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime

from app.models import (
    LinkedInApplicationConfirmation,
    LinkedInJobCard,
    LinkedInRawEmailMessage,
)
from app.sources.linkedin.utils import (
    canonical_linkedin_job_url,
    extract_easy_apply,
    extract_job_id_from_href,
    extract_work_mode,
    title_matches_exclusion,
)


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_observed_at(received_at: str | None) -> datetime | None:
    if not received_at:
        return None
    try:
        return parsedate_to_datetime(received_at)
    except Exception:
        return None


def looks_like_location(value: str) -> bool:
    lowered = value.lower()
    return any(
        cue in lowered
        for cue in [
            ", on",
            ", ontario",
            ", canada",
            "remote",
            "hybrid",
            "on-site",
            "onsite",
            "toronto",
            "scarborough",
            "markham",
            "mississauga",
        ]
    )


def looks_like_intro_or_noise(value: str) -> bool:
    lowered = value.lower()
    return any(
        phrase in lowered
        for phrase in [
            "your job alert for ",
            "new jobs match your preferences",
            "results from the new ai-powered job search",
            "based on your profile",
            "jobs like this are getting more attention",
            "see all jobs on linkedin",
        ]
    )


def looks_like_company(value: str) -> bool:
    if looks_like_intro_or_noise(value):
        return False
    if value.startswith("View job:"):
        return False
    return True


def extract_job_url(value: str) -> str | None:
    match = re.search(r"https://www\.linkedin\.com/\S+", value)
    if not match:
        return None
    return match.group(0).rstrip(").,")


def _extract_job_url_from_text(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        job_url = extract_job_url(value)
        if job_url:
            return canonical_linkedin_job_url(job_url)
    return None


def _confirmation_phrase_present(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        lowered = value.casefold()
        if "your application was sent to" in lowered:
            return "your application was sent to"
        if "application submitted" in lowered:
            return "application submitted"
        if "application sent" in lowered:
            return "application sent"
    return None


def _extract_company_from_confirmation_text(*values: str | None) -> str | None:
    patterns = [
        re.compile(r"your application was sent to\s+(.+?)(?:\.|$)", re.IGNORECASE),
        re.compile(r"application submitted to\s+(.+?)(?:\.|$)", re.IGNORECASE),
    ]
    for value in values:
        if not value:
            continue
        for pattern in patterns:
            match = pattern.search(value)
            if match:
                return _clean_line(match.group(1))
    return None


def _looks_like_html_noise(value: str) -> bool:
    lowered = value.casefold()
    return any(
        token in lowered
        for token in [
            "<",
            ">",
            "href=",
            "style=",
            "width=",
            "height=",
            "display:",
            "inline-block",
        ]
    )


def _extract_title_from_text_lines(value: str | None) -> str | None:
    if not value:
        return None
    for raw_line in value.splitlines():
        line = _clean_line(raw_line)
        if not line:
            continue
        match = re.match(r"job title:\s+(.+)$", line, re.IGNORECASE)
        if not match:
            continue
        candidate = _clean_line(match.group(1))
        if candidate and not _looks_like_html_noise(candidate):
            return candidate
    return None


def _extract_title_from_confirmation_text(*values: str | None) -> str | None:
    patterns = [
        re.compile(r"for the role of\s+(.+?)(?:\.|$)", re.IGNORECASE),
        re.compile(r"position:\s+(.+?)(?:\.|$)", re.IGNORECASE),
        re.compile(r"job title:\s+(.+?)(?:\.|$)", re.IGNORECASE),
    ]
    for value in values:
        if not value:
            continue
        for pattern in patterns:
            match = pattern.search(value)
            if match:
                candidate = _clean_line(match.group(1))
                if candidate and not _looks_like_html_noise(candidate):
                    return candidate
    return None


def to_job_card_from_email_block(
    block_lines: list[str],
    job_url: str,
    observed_at: datetime | None,
    title_exclude_contains: list[str],
) -> LinkedInJobCard | None:
    cleaned_lines = [_clean_line(line) for line in block_lines if _clean_line(line)]
    if len(cleaned_lines) < 3:
        return None

    title = cleaned_lines[0]
    if looks_like_intro_or_noise(title):
        return None
    if title_matches_exclusion(title, title_exclude_contains):
        return None

    company = cleaned_lines[1] if len(cleaned_lines) > 1 else None
    if not company or not looks_like_company(company):
        return None

    location_text = cleaned_lines[2] if len(cleaned_lines) > 2 and looks_like_location(cleaned_lines[2]) else None
    badge_start = 3 if location_text else 2
    badge_texts = cleaned_lines[badge_start:]

    return LinkedInJobCard(
        source="linkedin",
        source_type="email_notifications",
        observed_at=observed_at,
        linkedin_job_id=extract_job_id_from_href(job_url),
        job_url=canonical_linkedin_job_url(job_url),
        title=title,
        company=company,
        location_text=location_text,
        work_mode=extract_work_mode(location_text),
        easy_apply=extract_easy_apply(badge_texts),
        badges=badge_texts,
    )


def extract_job_cards_from_email(
    message: LinkedInRawEmailMessage,
    title_exclude_contains: list[str],
) -> list[LinkedInJobCard]:
    text_body = message.text_body or ""
    if not text_body:
        return []

    observed_at = parse_observed_at(message.received_at)
    block_lines: list[str] = []
    job_cards: list[LinkedInJobCard] = []

    for raw_line in text_body.splitlines():
        line = _clean_line(raw_line)
        if not line:
            continue
        if line.startswith("See all jobs on LinkedIn:"):
            break
        if set(line) == {"-"}:
            block_lines = []
            continue
        if line.startswith("View job:"):
            job_url = extract_job_url(line)
            if job_url:
                job_card = to_job_card_from_email_block(
                    block_lines,
                    job_url,
                    observed_at,
                    title_exclude_contains,
                )
                if job_card is not None:
                    job_cards.append(job_card)
            block_lines = []
            continue
        if not block_lines and looks_like_intro_or_noise(line):
            continue
        block_lines.append(line)

    return job_cards


def extract_application_confirmation_from_email(
    message: LinkedInRawEmailMessage,
) -> LinkedInApplicationConfirmation | None:
    confirmation_text = _confirmation_phrase_present(message.subject, message.text_body, message.html_body)
    if confirmation_text is None:
        return None

    job_url = _extract_job_url_from_text(message.text_body, message.html_body)
    linkedin_job_id = extract_job_id_from_href(job_url) if job_url else None
    company = _extract_company_from_confirmation_text(message.subject, message.text_body, message.html_body)
    title = _extract_title_from_text_lines(message.text_body) or _extract_title_from_confirmation_text(
        message.subject,
        message.text_body,
    )

    return LinkedInApplicationConfirmation(
        sequence_id=message.sequence_id,
        message_id=message.message_id,
        subject=message.subject,
        from_address=message.from_address,
        received_at=message.received_at,
        linkedin_job_id=linkedin_job_id,
        job_url=job_url,
        company=company,
        title=title,
        confirmation_text=confirmation_text,
    )
