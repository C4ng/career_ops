from __future__ import annotations

import logging

from playwright.sync_api import sync_playwright

from app.sources.linkedin.scraper.extract import detail_page_debug_payload, extract_detail_fields


logger = logging.getLogger(__name__)


def _load_job_detail(page, candidate: dict[str, object]) -> dict[str, object]:
    requested_job_url = str(candidate["job_url"])
    page.goto(requested_job_url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(1500)
    detail_fields = extract_detail_fields(page)
    logger.debug(
        "LinkedIn detail page probes",
        extra={
            "linkedin_job_id": candidate["linkedin_job_id"],
            "title": candidate["title"],
            "page": detail_page_debug_payload(page, requested_job_url=requested_job_url),
        },
    )
    return {
        "job_id": candidate["job_id"],
        "linkedin_job_id": candidate["linkedin_job_id"],
        "job_url": requested_job_url,
        "title": candidate["title"],
        "company": candidate["company"],
        **detail_fields,
    }


def fetch_linkedin_job_details(cdp_url: str, candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    if not candidates:
        return []

    results: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        try:
            page = context.new_page()
            try:
                for index, candidate in enumerate(candidates, start=1):
                    logger.info(
                        "LinkedIn detail fetch job started",
                        extra={
                            "job_index": index,
                            "job_count": len(candidates),
                            "linkedin_job_id": candidate["linkedin_job_id"],
                            "title": candidate["title"],
                            "company": candidate["company"],
                            "job_url": candidate["job_url"],
                        },
                    )
                    detail = _load_job_detail(page, candidate)
                    logger.info(
                        "LinkedIn detail fetch job completed",
                        extra={
                            "job_index": index,
                            "job_count": len(candidates),
                            "linkedin_job_id": detail["linkedin_job_id"],
                            "title": detail["title"],
                            "has_job_description": bool(detail["job_description"]),
                            "job_description_length": len(detail["job_description"] or ""),
                            "observed_posted_text": detail["observed_posted_text"],
                            "work_mode": detail["work_mode"],
                            "employment_type": detail["employment_type"],
                            "applicant_count_text": detail["applicant_count_text"],
                            "application_status_text": detail["application_status_text"],
                            "easy_apply": detail["easy_apply"],
                            "apply_link": detail["apply_link"],
                        },
                    )
                    results.append(detail)
            finally:
                page.close()
        finally:
            browser.close()
    return results
