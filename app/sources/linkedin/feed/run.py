from __future__ import annotations

import logging
from datetime import UTC, datetime

from playwright.sync_api import sync_playwright

from app.models import (
    LinkedInCollectionResult,
    LinkedInJobCard,
    LinkedInSourceConfig,
)

from .collection import collect_job_cards_from_page
from .dedupe import job_card_dedupe_key
from .query import build_source_url, source_page_step

logger = logging.getLogger(__name__)


def _build_collection_outputs(
    *,
    searched_at: datetime,
    source_type: str,
    source_url: str,
    cards_requested_total: int,
    unique_job_cards: list[LinkedInJobCard],
    title_filtered_total: int,
    title_filtered_titles: list[str],
    duplicates_skipped_total: int,
    stopped_reason: str,
    offsets_visited: list[int] | None = None,
    chunks: list[dict[str, object]] | None = None,
) -> LinkedInCollectionResult:
    runtime_result = LinkedInCollectionResult(
        searched_at=searched_at,
        source_type=source_type,
        source_url=source_url,
        cards_requested_total=cards_requested_total,
        unique_cards_total=len(unique_job_cards),
        title_filtered_total=title_filtered_total,
        title_filtered_titles=title_filtered_titles,
        duplicates_skipped_total=duplicates_skipped_total,
        offsets_visited=offsets_visited or [],
        stopped_reason=stopped_reason,
        chunks=chunks or [],
        job_cards=unique_job_cards,
    )
    return runtime_result


def _run_source_chunk(
    page,
    *,
    source_url: str,
    source_config: LinkedInSourceConfig,
    source_type: str,
    collect_limit: int,
) -> tuple[dict[str, object], list[LinkedInJobCard]]:
    page.goto(source_url, wait_until="domcontentloaded", timeout=30000)
    job_cards, collection_metrics = collect_job_cards_from_page(
        page,
        source_url=source_url,
        collect_limit=collect_limit,
        title_exclude_contains=source_config.title_exclude_contains,
        source_type=source_type,
    )
    chunk_summary = {
        "raw_nodes_matched": int(collection_metrics["raw_nodes_matched"] or 0),
        "raw_nodes_checked": int(collection_metrics["raw_nodes_checked"] or 0),
        "cards_extracted": int(collection_metrics["cards_extracted"] or 0),
        "title_filtered": int(collection_metrics["title_filtered"] or 0),
        "title_filtered_titles_in_chunk": collection_metrics.get("title_filtered_titles_in_chunk", []),
        "final_populated_rows_in_chunk": collection_metrics["final_populated_rows"],
    }
    return chunk_summary, job_cards


def run_linkedin_source(
    source_config: LinkedInSourceConfig,
    source_type: str,
) -> LinkedInCollectionResult:
    base_source_url = build_source_url(source_config, source_type, 0)
    collect_limit = source_config.collect_limit
    logger.info(
        "Starting LinkedIn source run",
        extra={
            "source_type": source_type,
            "collect_limit": collect_limit,
            "max_offsets": source_config.max_offsets,
            "source_url": base_source_url,
        },
    )

    chunk_summaries: list[dict[str, object]] = []
    unique_job_cards: list[LinkedInJobCard] = []
    seen_keys: set[str] = set()
    offsets_visited: list[int] = []
    title_filtered_total = 0
    title_filtered_titles: list[str] = []
    duplicates_skipped_total = 0

    searched_at = datetime.now(UTC)
    stopped_reason = "collect_limit_reached"
    page_step = source_page_step(source_config, source_type)
    max_offsets = source_config.max_offsets

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(source_config.cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        try:
            for offset_index in range(0, max_offsets):
                if len(unique_job_cards) >= collect_limit:
                    break

                start = offset_index * page_step if page_step is not None else 0
                source_url = build_source_url(source_config, source_type, start)
                offsets_visited.append(start)
                remaining_target = max(collect_limit - len(unique_job_cards), 1)
                page = context.new_page()
                try:
                    chunk_summary, chunk_job_cards = _run_source_chunk(
                        page,
                        source_url=source_url,
                        source_config=source_config,
                        source_type=source_type,
                        collect_limit=remaining_target,
                    )
                finally:
                    page.close()

                chunk_summary["start"] = start

                duplicates_skipped = 0
                unique_cards_kept = 0
                for job_card in chunk_job_cards:
                    key = job_card_dedupe_key(job_card)
                    if not key:
                        logger.warning(
                            "Job card has no dedupe key, skipping",
                            extra={"title": job_card.title, "company": job_card.company},
                        )
                        continue
                    if key in seen_keys:
                        duplicates_skipped += 1
                        continue
                    seen_keys.add(key)
                    unique_job_cards.append(job_card)
                    unique_cards_kept += 1
                    if len(unique_job_cards) >= collect_limit:
                        break

                duplicates_skipped_total += duplicates_skipped
                title_filtered_total += int(chunk_summary.get("title_filtered", 0))
                for title in chunk_summary.get("title_filtered_titles_in_chunk", []):
                    if title and title not in title_filtered_titles:
                        title_filtered_titles.append(title)
                chunk_summary["duplicates_skipped"] = duplicates_skipped
                chunk_summary["unique_cards_kept"] = unique_cards_kept
                chunk_summaries.append(chunk_summary)
                logger.info(
                    "LinkedIn chunk processed",
                    extra={
                        "source_type": source_type,
                        "start": start,
                        "raw_nodes_matched": chunk_summary.get("raw_nodes_matched"),
                        "raw_nodes_checked": chunk_summary.get("raw_nodes_checked"),
                        "duplicates_skipped": duplicates_skipped,
                        "unique_cards_kept": unique_cards_kept,
                        "title_filtered": chunk_summary.get("title_filtered"),
                        "title_filtered_titles_in_chunk": chunk_summary.get("title_filtered_titles_in_chunk", []),
                        "final_populated_rows_in_chunk": chunk_summary.get("final_populated_rows_in_chunk"),
                    },
                )

                if len(unique_job_cards) >= collect_limit:
                    stopped_reason = "collect_limit_reached"
                    break
                if int(chunk_summary.get("raw_nodes_matched", 0)) < page_step:
                    stopped_reason = "chunk_smaller_than_page_step"
                    break
                if unique_cards_kept == 0:
                    stopped_reason = "no_new_unique_cards_in_chunk"
                    break
            else:
                stopped_reason = "max_offset_limit_reached"
        finally:
            browser.close()

    result = _build_collection_outputs(
        searched_at=searched_at,
        source_type=source_type,
        source_url=base_source_url,
        cards_requested_total=collect_limit,
        unique_job_cards=unique_job_cards,
        title_filtered_total=title_filtered_total,
        title_filtered_titles=title_filtered_titles,
        duplicates_skipped_total=duplicates_skipped_total,
        stopped_reason=stopped_reason,
        offsets_visited=offsets_visited,
        chunks=chunk_summaries,
    )
    logger.info(
        "Finished LinkedIn source run",
        extra={
            "source_type": source_type,
            "collect_limit": collect_limit,
            "unique_cards_total": result.unique_cards_total,
            "title_filtered_total": result.title_filtered_total,
            "duplicates_skipped_total": result.duplicates_skipped_total,
            "stopped_reason": result.stopped_reason,
        },
    )
    return result
