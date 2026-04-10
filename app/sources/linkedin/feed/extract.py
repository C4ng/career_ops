from __future__ import annotations

import re
from datetime import datetime

from app.models import LinkedInJobCard, LinkedInRawCard
from app.sources.linkedin.utils import (
    canonical_linkedin_job_url,
    clean_text,
    extract_easy_apply,
    extract_job_id_from_href,
    extract_work_mode,
    title_matches_exclusion,
)


def extract_posted_text(badge_texts: list[str]) -> str | None:
    patterns = (
        r"\b\d+\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago\b",
        r"\breposted\s+\d+\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago\b",
        r"\btoday\b",
        r"\byesterday\b",
    )
    for badge_text in badge_texts:
        lowered = badge_text.lower()
        if any(re.search(pattern, lowered) for pattern in patterns):
            return badge_text
    return None


def extract_salary_text(card_text: str | None) -> str | None:
    if not card_text:
        return None
    salary_patterns = [
        r"(?:CA\$|C\$|\$|US\$|USD|CAD)\s?\d[\d.,KkMm]*(?:/\w+)?\s*-\s*(?:CA\$|C\$|\$|US\$|USD|CAD)?\s?\d[\d.,KkMm]*(?:/\w+)?",
        r"(?:CA\$|C\$|\$|US\$|USD|CAD)\s?\d[\d.,KkMm]*(?:/\w+)",
    ]
    for pattern in salary_patterns:
        match = re.search(pattern, card_text)
        if match:
            return match.group(0)
    return None

def clean_badges(badge_texts: list[str], posted_text: str | None) -> list[str]:
    cleaned: list[str] = []
    for badge_text in badge_texts:
        if posted_text and badge_text == posted_text:
            continue
        cleaned.append(badge_text)
    return cleaned


def to_job_card(
    raw_card: LinkedInRawCard,
    observed_at: datetime,
    *,
    source_type: str = "search",
) -> LinkedInJobCard:
    posted_text = extract_posted_text(raw_card.badge_texts)
    return LinkedInJobCard(
        observed_at=observed_at,
        source_type=source_type,
        linkedin_job_id=raw_card.current_job_id_guess,
        job_url=canonical_linkedin_job_url(raw_card.href),
        title=raw_card.title_text,
        company=raw_card.company_text,
        location_text=raw_card.location_text,
        work_mode=extract_work_mode(raw_card.location_text),
        observed_posted_text=posted_text,
        salary_text=extract_salary_text(raw_card.card_text),
        easy_apply=extract_easy_apply(raw_card.badge_texts),
        badges=clean_badges(raw_card.badge_texts, posted_text),
        raw_card_text=raw_card.card_text,
    )


def should_drop_raw_card(raw_card: LinkedInRawCard) -> str | None:
    if raw_card.title_text or raw_card.href or raw_card.current_job_id_guess or raw_card.card_text:
        return None
    return "empty_placeholder_row"


def row_has_content(card) -> bool:
    href = None
    link_locator = card.locator("a").first
    if link_locator.count():
        href = link_locator.get_attribute("href")
    text = clean_text(card.inner_text())
    title = clean_text(card.locator("strong").first.text_content()) if card.locator("strong").count() else None
    return bool(href or text or title)


def parse_row_card(card, index: int, include_card_html: bool) -> LinkedInRawCard:
    title_text = clean_text(card.locator("strong").first.text_content()) if card.locator("strong").count() else None
    if not title_text and card.locator("a").count():
        title_text = clean_text(card.locator("a").first.text_content())

    company_text = None
    for selector in [".artdeco-entity-lockup__subtitle", ".base-search-card__subtitle", "h4"]:
        locator = card.locator(selector)
        if locator.count():
            company_text = clean_text(locator.first.text_content())
            if company_text:
                break

    location_text = None
    for selector in [".artdeco-entity-lockup__caption", ".job-search-card__location", ".base-search-card__metadata"]:
        locator = card.locator(selector)
        if locator.count():
            location_text = clean_text(locator.first.text_content())
            if location_text:
                break

    badge_texts: list[str] = []
    badge_locator = card.locator(".job-card-container__footer-item, .job-search-card__listlabel, .artdeco-entity-lockup__insight")
    for badge_index in range(badge_locator.count()):
        badge_text = clean_text(badge_locator.nth(badge_index).text_content())
        if badge_text and badge_text not in badge_texts:
            badge_texts.append(badge_text)

    href = None
    link_locator = card.locator("a").first
    if link_locator.count():
        href = link_locator.get_attribute("href")

    return LinkedInRawCard(
        index=index,
        title_text=title_text,
        company_text=company_text,
        location_text=location_text,
        badge_texts=badge_texts,
        href=href,
        current_job_id_guess=extract_job_id_from_href(href),
        card_text=clean_text(card.inner_text()),
        card_html=card.inner_html() if include_card_html else None,
    )


def to_dropped_raw_card_payload(raw_card: LinkedInRawCard, drop_reason: str) -> dict[str, object]:
    return {
        "index": raw_card.index,
        "drop_reason": drop_reason,
        "href": raw_card.href,
        "current_job_id_guess": raw_card.current_job_id_guess,
        "card_text": raw_card.card_text,
        "card_html": raw_card.card_html,
    }
