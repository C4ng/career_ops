from __future__ import annotations

from playwright.sync_api import Page

from app.sources.linkedin.utils import clean_text


def preview_text(value: str | None, limit: int = 1200) -> str | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    return cleaned[:limit]


def selector_counts(page: Page, selectors: list[str]) -> dict[str, int]:
    return {selector: page.locator(selector).count() for selector in selectors}


def selector_text_samples(page: Page, selectors: list[str], per_selector_limit: int = 2) -> dict[str, list[str]]:
    samples: dict[str, list[str]] = {}
    for selector in selectors:
        locator = page.locator(selector)
        selector_samples: list[str] = []
        for index in range(min(locator.count(), per_selector_limit)):
            sample = preview_text(locator.nth(index).inner_text(), limit=300)
            if sample:
                selector_samples.append(sample)
        if selector_samples:
            samples[selector] = selector_samples
    return samples


def selector_html_samples(page: Page, selectors: list[str], per_selector_limit: int = 2) -> dict[str, list[str]]:
    samples: dict[str, list[str]] = {}
    for selector in selectors:
        locator = page.locator(selector)
        selector_samples: list[str] = []
        for index in range(min(locator.count(), per_selector_limit)):
            sample = preview_text(locator.nth(index).evaluate("node => node.outerHTML"), limit=1200)
            if sample:
                selector_samples.append(sample)
        if selector_samples:
            samples[selector] = selector_samples
    return samples
