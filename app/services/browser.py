from __future__ import annotations

import logging
from playwright.sync_api import sync_playwright

from app.models import LinkedInConnectionConfig, LinkedInConnectionResult

logger = logging.getLogger(__name__)

PAGE_LOAD_TIMEOUT_MS = 20_000
POST_NAVIGATION_SETTLE_MS = 1500


def verify_linkedin_connection(config: LinkedInConnectionConfig) -> LinkedInConnectionResult:
    logger.info("Verifying LinkedIn connection via CDP", extra={"cdp_url": config.cdp_url})
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(config.cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            try:
                page.goto(config.test_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
                page.wait_for_timeout(POST_NAVIGATION_SETTLE_MS)
                current_url = page.url
                page_title = page.title()
                linkedin_accessible = config.expected_domain_contains in current_url
                not_on_login_signup_page = "login" not in current_url and "signup" not in current_url
                result = LinkedInConnectionResult(
                    success=linkedin_accessible and not_on_login_signup_page,
                    cdp_url=config.cdp_url,
                    test_url=config.test_url,
                    expected_domain_contains=config.expected_domain_contains,
                    current_url=current_url,
                    page_title=page_title,
                    browser_connected=True,
                    linkedin_accessible=linkedin_accessible,
                    not_on_login_signup_page=not_on_login_signup_page,
                )
                logger.info(
                    "LinkedIn connection verification finished",
                    extra={
                        "success": result.success,
                        "current_url": result.current_url,
                        "linkedin_accessible": result.linkedin_accessible,
                        "not_on_login_signup_page": result.not_on_login_signup_page,
                    },
                )
                return result
            finally:
                page.close()
                browser.close()
    except Exception as exc:
        logger.exception("LinkedIn connection verification failed")
        return LinkedInConnectionResult(
            success=False,
            cdp_url=config.cdp_url,
            test_url=config.test_url,
            expected_domain_contains=config.expected_domain_contains,
            error=str(exc),
        )
