from __future__ import annotations

import re
from urllib.parse import urlparse

from playwright.sync_api import Page

from app.sources.linkedin.debug import (
    preview_text,
    selector_counts,
    selector_html_samples,
    selector_text_samples,
)
from app.sources.linkedin.utils import clean_text, normalize_linkedin_apply_link


DESCRIPTION_SELECTORS = [
    ".jobs-description__content",
    ".jobs-box__html-content",
    ".jobs-description-content__text",
    "#job-details",
]

DEBUG_SELECTORS = [
    "h1",
    ".job-details-jobs-unified-top-card__company-name",
    ".job-details-jobs-unified-top-card__primary-description-container",
    ".job-details-jobs-unified-top-card__job-insight",
    *DESCRIPTION_SELECTORS,
]

EMPLOYMENT_TYPE_VALUES = [
    "Full-time",
    "Part-time",
    "Contract",
    "Temporary",
    "Internship",
    "Apprenticeship",
    "Volunteer",
]

APPLICATION_STATUS_PHRASES = [
    "No longer accepting applications",
    "Actively reviewing applications",
]

MIN_DESCRIPTION_LENGTH = 120
MAX_APPLY_LINK_ANCHORS = 30


def _normalized_body_text(page: Page) -> str | None:
    body_locator = page.locator("body")
    if not body_locator.count():
        return None
    return body_locator.inner_text()


def _extract_job_description_from_body_text(body_text: str | None) -> str | None:
    cleaned_body = clean_text(body_text)
    if not cleaned_body:
        return None

    match = re.search(r"About the job\s+(.*)", cleaned_body, flags=re.IGNORECASE)
    if not match:
        return None

    description = match.group(1)
    stop_markers = [
        "Seniority level",
        "Employment type",
        "Job function",
        "Industries",
    ]
    immediate_stop_markers = [
        "Referrals increase your chances",
        "Set alert for similar jobs",
        "Get notified about new",
        "Sign in to create your job alert",
        "People also viewed",
        "Similar jobs",
        "Report this job",
    ]
    end_index = len(description)
    lowered_description = description.lower()
    for marker in stop_markers:
        marker_index = lowered_description.find(marker.lower())
        if marker_index >= 200:
            end_index = min(end_index, marker_index)
    for marker in immediate_stop_markers:
        marker_index = lowered_description.find(marker.lower())
        if marker_index != -1:
            end_index = min(end_index, marker_index)
    candidate = clean_text(description[:end_index])
    if candidate and len(candidate) >= MIN_DESCRIPTION_LENGTH:
        return candidate
    return candidate


def _top_card_text(body_text: str | None) -> str | None:
    if not body_text:
        return None
    idx = body_text.lower().find("about the job")
    top_text = body_text if idx < 0 else body_text[:idx]
    return clean_text(top_text)


def extract_observed_posted_text_from_body_text(body_text: str | None) -> str | None:
    top_text = _top_card_text(body_text)
    if not top_text:
        return None
    match = re.search(
        r"(Reposted\s+\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago|\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago|Today|Yesterday)",
        top_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return clean_text(match.group(1))


def extract_applicant_count_text_from_body_text(body_text: str | None) -> str | None:
    top_text = _top_card_text(body_text)
    if not top_text:
        return None
    match = re.search(
        r"(Over\s+\d+\s+(?:applicants|people clicked apply)|\d+\s+(?:applicants|people clicked apply))",
        top_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return clean_text(match.group(1))


def extract_work_mode_from_body_text(body_text: str | None) -> str | None:
    top_text = _top_card_text(body_text)
    if not top_text:
        return None
    lowered = top_text.lower()
    if "remote" in lowered:
        return "remote"
    if "hybrid" in lowered:
        return "hybrid"
    if "on-site" in lowered or "onsite" in lowered:
        return "on_site"
    return None


def extract_employment_type_from_body_text(body_text: str | None) -> str | None:
    top_text = _top_card_text(body_text)
    if not top_text:
        return None
    for value in EMPLOYMENT_TYPE_VALUES:
        if re.search(rf"\b{re.escape(value)}\b", top_text, flags=re.IGNORECASE):
            return value
    return None


def extract_application_status_text_from_body_text(body_text: str | None) -> str | None:
    top_text = _top_card_text(body_text)
    if not top_text:
        return None
    for phrase in APPLICATION_STATUS_PHRASES:
        if phrase.lower() in top_text.lower():
            return phrase
    return None


def extract_easy_apply_from_body_text(body_text: str | None) -> bool:
    top_text = _top_card_text(body_text)
    if not top_text:
        return False
    return "easy apply" in top_text.lower()


def extract_apply_link(page: Page) -> str | None:
    locator = page.locator("a")
    for index in range(min(locator.count(), MAX_APPLY_LINK_ANCHORS)):
        anchor = locator.nth(index)
        href = anchor.get_attribute("href")
        if not href:
            continue
        aria_label = (anchor.get_attribute("aria-label") or "").lower()
        text = clean_text(anchor.inner_text()) or ""
        lowered_text = text.lower()
        is_apply_target = (
            "/jobs/view/" in href and "/apply/" in href
            or "/safety/go/" in href
            or "easy apply" in aria_label
            or "apply on company website" in aria_label
            or lowered_text == "apply"
            or lowered_text == "easy apply"
        )
        if not is_apply_target:
            continue
        normalized = normalize_linkedin_apply_link(href)
        if normalized:
            parsed = urlparse(normalized)
            is_linkedin_easy_apply = (
                parsed.netloc.endswith("linkedin.com")
                and "/jobs/view/" in parsed.path
                and "/apply/" in parsed.path
            )
            is_external_apply = not parsed.netloc.endswith("linkedin.com")
            if is_linkedin_easy_apply or is_external_apply:
                return normalized
    return None


def _best_text_for_selector(page: Page, selector: str) -> str | None:
    locator = page.locator(selector)
    best_value: str | None = None
    for index in range(locator.count()):
        candidate = clean_text(locator.nth(index).inner_text())
        if not candidate:
            continue
        if best_value is None or len(candidate) > len(best_value):
            best_value = candidate
    return best_value


def extract_job_description(page: Page) -> str | None:
    for selector in DESCRIPTION_SELECTORS:
        value = _best_text_for_selector(page, selector)
        if value and len(value) >= MIN_DESCRIPTION_LENGTH:
            return value
    for selector in DESCRIPTION_SELECTORS:
        value = _best_text_for_selector(page, selector)
        if value:
            return value
    body_locator = page.locator("body")
    body_text = body_locator.inner_text() if body_locator.count() else None
    return _extract_job_description_from_body_text(body_text)


def extract_detail_fields(page: Page) -> dict[str, object]:
    body_text = _normalized_body_text(page)
    return {
        "job_description": extract_job_description(page),
        "apply_link": extract_apply_link(page),
        "observed_posted_text": extract_observed_posted_text_from_body_text(body_text),
        "applicant_count_text": extract_applicant_count_text_from_body_text(body_text),
        "work_mode": extract_work_mode_from_body_text(body_text),
        "employment_type": extract_employment_type_from_body_text(body_text),
        "application_status_text": extract_application_status_text_from_body_text(body_text),
        "easy_apply": extract_easy_apply_from_body_text(body_text),
    }


def detail_page_debug_payload(page: Page, *, requested_job_url: str) -> dict[str, object]:
    body_locator = page.locator("body")
    body_text = _normalized_body_text(page)
    body_html = body_locator.evaluate("node => node.outerHTML") if body_locator.count() else None
    detail_fields = extract_detail_fields(page)
    return {
        "requested_job_url": requested_job_url,
        "current_url": page.url,
        "page_title": page.title(),
        "body_text_preview": preview_text(body_text, limit=2000),
        "body_html_preview": preview_text(body_html, limit=2000),
        "selector_counts": selector_counts(page, DEBUG_SELECTORS),
        "selector_text_samples": selector_text_samples(page, DEBUG_SELECTORS),
        "selector_html_samples": selector_html_samples(page, DEBUG_SELECTORS, per_selector_limit=1),
        "parsed_detail_fields": {
            **detail_fields,
            "job_description": preview_text(detail_fields["job_description"], limit=1600),
        },
    }
