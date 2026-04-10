from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from playwright.sync_api import Page

from app.models import LinkedInJobCard
from app.sources.linkedin.utils import title_matches_exclusion

from app.sources.linkedin.debug import (
    preview_text,
    selector_counts,
    selector_html_samples,
    selector_text_samples,
)
from .expand import (
    CARD_SELECTORS,
    READY_SIGNAL_SELECTORS,
    card_locator,
    expand_result_list,
    wait_for_jobs_page_render,
)
from .extract import (
    parse_row_card,
    should_drop_raw_card,
    to_dropped_raw_card_payload,
    to_job_card,
)

logger = logging.getLogger(__name__)


def collect_job_cards_from_page(
    page: Page,
    *,
    source_url: str,
    collect_limit: int,
    title_exclude_contains: list[str],
    source_type: str,
) -> tuple[list[LinkedInJobCard], dict[str, Any]]:
    searched_at = datetime.now(UTC)
    debug_enabled = logger.isEnabledFor(logging.DEBUG)

    wait_for_jobs_page_render(page)

    ready_signal_counts = selector_counts(page, READY_SIGNAL_SELECTORS) if debug_enabled else {}
    selector_counts_payload = selector_counts(page, CARD_SELECTORS) if debug_enabled else {}
    selector_text_samples_payload = selector_text_samples(page, CARD_SELECTORS) if debug_enabled else {}
    selector_html_samples_payload = selector_html_samples(page, CARD_SELECTORS) if debug_enabled else {}
    chosen_selector, cards_locator = card_locator(page, CARD_SELECTORS)
    raw_nodes_matched = cards_locator.count()
    list_container_selector, list_container_metrics, expansion_progress, raw_nodes_matched = expand_result_list(
        page, cards_locator, raw_nodes_matched, collect_limit
    )

    cards = []
    dropped_cards: list[dict[str, object]] = []
    title_filtered_cards: list[dict[str, object]] = []
    raw_nodes_checked = 0
    title_filtered = 0
    title_filtered_titles_in_chunk: list[str] = []

    for index in range(cards_locator.count()):
        if len(cards) >= collect_limit:
            break
        raw_nodes_checked += 1
        raw_card = parse_row_card(cards_locator.nth(index), index + 1, debug_enabled)
        drop_reason = should_drop_raw_card(raw_card)
        if drop_reason:
            dropped_cards.append(to_dropped_raw_card_payload(raw_card, drop_reason))
            continue
        excluded_term = title_matches_exclusion(raw_card.title_text, title_exclude_contains)
        if excluded_term:
            title_filtered += 1
            if raw_card.title_text and raw_card.title_text not in title_filtered_titles_in_chunk:
                title_filtered_titles_in_chunk.append(raw_card.title_text)
            title_filtered_cards.append(
                {
                    "index": raw_card.index,
                    "drop_reason": "title_excluded",
                    "matched_term": excluded_term,
                    "title_text": raw_card.title_text,
                    "company_text": raw_card.company_text,
                    "href": raw_card.href,
                    "current_job_id_guess": raw_card.current_job_id_guess,
                }
            )
            continue
        cards.append(raw_card)

    job_cards = [to_job_card(card, searched_at, source_type=source_type) for card in cards]
    final_populated_rows = expansion_progress[-1]["populated_rows"] if expansion_progress else None
    collection_metrics: dict[str, Any] = {
        "raw_nodes_matched": raw_nodes_matched,
        "raw_nodes_checked": raw_nodes_checked,
        "cards_extracted": len(cards),
        "title_filtered": title_filtered,
        "title_filtered_titles_in_chunk": title_filtered_titles_in_chunk,
        "final_populated_rows": final_populated_rows,
    }
    if debug_enabled:
        logger.debug(
            "Chunk debug probes",
            extra={
                "current_url": page.url,
                "page_title": page.title(),
                "selector_counts": selector_counts_payload,
                "selector_text_samples": selector_text_samples_payload,
                "selector_html_samples": selector_html_samples_payload,
                "chosen_card_selector": chosen_selector,
                "list_container_selector": list_container_selector,
                "list_container_metrics": list_container_metrics,
                "ready_signal_counts": ready_signal_counts,
                "expansion_progress": expansion_progress,
                "dropped_cards": dropped_cards,
                "title_filtered_cards": title_filtered_cards,
                "body_text_preview": preview_text(page.text_content("body")),
                "body_html_preview": preview_text(page.inner_html("body")),
            },
        )

    logger.info(
        "Collected chunk",
        extra={
            "source_url": source_url,
            "raw_nodes_matched": raw_nodes_matched,
            "raw_nodes_checked": raw_nodes_checked,
            "cards_extracted": len(cards),
            "title_filtered": title_filtered,
            "final_populated_rows": final_populated_rows,
            "collect_limit": collect_limit,
        },
    )
    return job_cards, collection_metrics
