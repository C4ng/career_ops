from __future__ import annotations

from playwright.sync_api import Page

from .extract import row_has_content

# Timing constants (milliseconds)
PRE_RENDER_SETTLE_MS = 1500
READY_SIGNAL_TIMEOUT_MS = 2500
POST_RENDER_SETTLE_MS = 1500
SCROLL_SETTLE_MS = 1200

# Scroll expansion limits
MAX_SCROLL_ATTEMPTS = 8
MAX_STAGNANT_PASSES = 2

CARD_SELECTORS = [
    "li[data-occludable-job-id]",
    ".scaffold-layout__list > div > ul > li",
    "li.jobs-search-results__list-item",
    "ul.scaffold-layout__list-container li",
    ".jobs-search-results-list__list-item",
    ".job-card-container",
    "[data-job-id]",
]

READY_SIGNAL_SELECTORS = [
    "main",
    ".jobs-search-results-list",
    ".jobs-search-results-list__list-item",
    ".job-card-container",
    ".scaffold-layout__list",
    ".jobs-search-two-pane__wrapper",
]

LIST_CONTAINER_SELECTORS = [
    ".scaffold-layout__list > div",
    ".scaffold-layout__list",
    ".jobs-search-results-list",
    ".scaffold-layout__list-container",
    ".jobs-search-results-list__list-container",
]


def wait_for_jobs_page_render(page: Page) -> None:
    page.wait_for_timeout(PRE_RENDER_SETTLE_MS)
    for selector in READY_SIGNAL_SELECTORS:
        try:
            page.wait_for_selector(selector, timeout=READY_SIGNAL_TIMEOUT_MS)
            break
        except Exception:
            continue
    page.wait_for_timeout(POST_RENDER_SETTLE_MS)


def card_locator(page: Page, card_selectors: list[str]):
    for selector in card_selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            return selector, locator
    fallback_selector = card_selectors[0]
    return fallback_selector, page.locator(fallback_selector)


def container_metrics(locator) -> dict[str, int | bool]:
    return locator.evaluate(
        """node => ({
            scrollTop: Math.floor(node.scrollTop || 0),
            scrollHeight: Math.floor(node.scrollHeight || 0),
            clientHeight: Math.floor(node.clientHeight || 0),
            isScrollable: (node.scrollHeight || 0) > (node.clientHeight || 0)
        })"""
    )


def list_container_locator(page: Page):
    selector_metrics: dict[str, dict[str, int | bool]] = {}
    best_scrollable: tuple[str, object, int] | None = None
    for selector in LIST_CONTAINER_SELECTORS:
        locator = page.locator(selector)
        if locator.count() > 0:
            first = locator.first
            metrics = container_metrics(first)
            selector_metrics[selector] = metrics
            if metrics["isScrollable"]:
                scroll_room = int(metrics["scrollHeight"]) - int(metrics["clientHeight"])
                if best_scrollable is None or scroll_room > best_scrollable[2]:
                    best_scrollable = (selector, first, scroll_room)
    if best_scrollable is not None:
        return best_scrollable[0], best_scrollable[1], selector_metrics
    body = page.locator("body").first
    selector_metrics["body"] = container_metrics(body)
    return "body", body, selector_metrics


def count_populated_rows(cards_locator) -> tuple[int, int]:
    raw_nodes_matched = cards_locator.count()
    populated = 0
    for index in range(raw_nodes_matched):
        if row_has_content(cards_locator.nth(index)):
            populated += 1
    return raw_nodes_matched, populated


def expand_result_list(page: Page, cards_locator, raw_nodes_matched: int, target_count: int):
    list_container_selector, list_container, list_container_metrics = list_container_locator(page)
    expansion_progress: list[dict[str, int | bool | None]] = []

    def snapshot(scroll_attempt: int):
        metrics = list_container.evaluate(
            """node => ({
                scrollTop: Math.floor(node.scrollTop || 0),
                scrollHeight: Math.floor(node.scrollHeight || 0),
                clientHeight: Math.floor(node.clientHeight || 0)
            })"""
        )
        current_raw_nodes_matched, populated_rows = count_populated_rows(cards_locator)
        payload = {
            "scroll_attempt": scroll_attempt,
            "raw_nodes_matched": current_raw_nodes_matched,
            "populated_rows": populated_rows,
            "scroll_top": metrics["scrollTop"],
            "scroll_height": metrics["scrollHeight"],
            "client_height": metrics["clientHeight"],
            "reached_bottom": metrics["scrollTop"] + metrics["clientHeight"] >= metrics["scrollHeight"],
        }
        expansion_progress.append(payload)
        return current_raw_nodes_matched, populated_rows, payload

    raw_nodes_matched, populated_rows, last_snapshot = snapshot(0)
    stagnant_passes = 0

    for scroll_attempt in range(1, MAX_SCROLL_ATTEMPTS + 1):
        if populated_rows >= target_count or last_snapshot["reached_bottom"]:
            break
        list_container.evaluate(
            """(node) => {
                const nextTop = Math.min(
                    (node.scrollTop || 0) + Math.max(node.clientHeight || 0, 400),
                    node.scrollHeight || 0
                );
                node.scrollTop = nextTop;
            }"""
        )
        page.wait_for_timeout(SCROLL_SETTLE_MS)
        raw_nodes_matched, populated_rows, new_snapshot = snapshot(scroll_attempt)
        stagnant_passes = stagnant_passes + 1 if populated_rows == last_snapshot["populated_rows"] else 0
        last_snapshot = new_snapshot
        if stagnant_passes >= MAX_STAGNANT_PASSES:
            break

    return list_container_selector, list_container_metrics, expansion_progress, raw_nodes_matched
