from __future__ import annotations

import logging
from typing import Iterable
from urllib.parse import urlparse

from playwright.sync_api import Browser, Page

from app.application.easy_apply.parse import normalize_apply_text

logger = logging.getLogger(__name__)

BODY_TEXT_LIMIT = 12_000


def page_text_contains_my_jobs_applied_signal(body_text: str, *, title: str, company: str) -> bool:
    normalized = normalize_apply_text(body_text)
    return (
        "my jobs" in normalized
        and "applied" in normalized
        and normalize_apply_text(title) in normalized
        and normalize_apply_text(company) in normalized
    )


def page_text_contains_job_page_applied_signal(body_text: str, *, title: str, company: str) -> bool:
    normalized = normalize_apply_text(body_text)
    return (
        "application status" in normalized
        and "application submitted" in normalized
        and normalize_apply_text(title) in normalized
        and normalize_apply_text(company) in normalized
    )


def _find_my_jobs_pages(browser: Browser) -> list[Page]:
    matches: list[Page] = []
    for context in browser.contexts:
        for page in context.pages:
            try:
                if "linkedin.com/my-items/saved-jobs" in (page.url or ""):
                    matches.append(page)
            except Exception:
                logger.debug("Failed to check page URL for my-jobs match", exc_info=True)
                continue
    return matches


def _job_page_matches_candidate(page: Page, *, linkedin_job_id: str, job_url: str | None) -> bool:
    page_url = page.url or ""
    if linkedin_job_id and linkedin_job_id in page_url:
        return True
    if job_url:
        try:
            candidate_path = urlparse(job_url).path
            page_path = urlparse(page_url).path
            if candidate_path and page_path and candidate_path == page_path:
                return True
        except Exception:
            return False
    return False


def verify_submitted_applications_in_linkedin_ui(
    browser: Browser,
    candidates: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    confirmations: list[dict[str, object]] = []
    my_jobs_pages = _find_my_jobs_pages(browser)
    my_jobs_texts: list[str] = []
    for page in my_jobs_pages:
        try:
            my_jobs_texts.append(page.locator("body").inner_text()[:BODY_TEXT_LIMIT])
        except Exception:
            logger.debug("Failed to read my-jobs page body text", exc_info=True)
            continue

    for candidate in candidates:
        title = str(candidate.get("title") or "")
        company = str(candidate.get("company") or "")
        linkedin_job_id = str(candidate.get("linkedin_job_id") or "")
        job_url = str(candidate.get("job_url") or "")
        matched_page_url: str | None = None
        source_type: str | None = None

        for context in browser.contexts:
            for page in context.pages:
                try:
                    if not _job_page_matches_candidate(page, linkedin_job_id=linkedin_job_id, job_url=job_url):
                        continue
                    body_text = page.locator("body").inner_text()[:BODY_TEXT_LIMIT]
                    if page_text_contains_job_page_applied_signal(body_text, title=title, company=company):
                        source_type = "linkedin_job_page_ui"
                        matched_page_url = page.url
                        break
                except Exception:
                    logger.debug("Failed to check job page for applied signal", exc_info=True)
                    continue
            if source_type:
                break

        if source_type is None and my_jobs_texts and any(
            page_text_contains_my_jobs_applied_signal(text, title=title, company=company)
            for text in my_jobs_texts
        ):
            source_type = "linkedin_my_jobs_applied_ui"
            matched_page_url = my_jobs_pages[0].url if my_jobs_pages else None

        confirmations.append(
            {
                "application_id": candidate["application_id"],
                "linkedin_job_id": linkedin_job_id,
                "confirmed": bool(source_type),
                "source_type": source_type,
                "job_url": job_url,
                "matched_page_url": matched_page_url,
            }
        )
    return confirmations
