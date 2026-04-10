from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    _HERE = Path(__file__).resolve()
    _REPO_ROOT = next((parent for parent in _HERE.parents if (parent / "pyproject.toml").exists()), _HERE.parents[2])
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.logging_setup import get_active_log_paths, setup_logging
from app.settings import (
    ROOT as APP_ROOT,
    load_linkedin_source_config,
    load_sqlite_config,
)
from app.sources.linkedin.log_payloads import collection_result_payload_for_logging
from app.sources.linkedin.feed import run_linkedin_source
from app.services.storage import connect_sqlite, initialize_schema, persist_linkedin_job_cards, resolve_db_path


ROOT = APP_ROOT


def _config_for_source(source_config, source_type: str) -> dict[str, object]:
    payload = {
        "source_type": [source_type],
        "cdp_url": source_config.cdp_url,
        "keyword_search_page_step": source_config.keyword_search_page_step,
        "recommended_feed_page_step": source_config.recommended_feed_page_step,
        "title_exclude_contains": source_config.title_exclude_contains,
        "collect_limit": source_config.collect_limit,
        "max_offsets": source_config.max_offsets,
    }
    if source_type == "keyword_search" and source_config.keyword_search is not None:
        payload["keyword_search"] = source_config.keyword_search.model_dump(mode="json")
    if source_type == "recommended_feed" and source_config.recommended_feed is not None:
        payload["recommended_feed"] = source_config.recommended_feed.model_dump(mode="json")
    return payload


def run_source() -> dict[str, object]:
    source_config = load_linkedin_source_config()
    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(ROOT, sqlite_config)
    log_paths = get_active_log_paths() or setup_logging("linkedin_source")
    logger = logging.getLogger(__name__)
    runs: list[dict[str, object]] = []
    logger.info("LinkedIn browser source config", extra={"config": source_config.model_dump(mode="json")})
    logger.info("LinkedIn browser storage config", extra={"storage": {"db_path": str(db_path)}})

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        for source_type in source_config.source_type:
            source_config_payload = _config_for_source(source_config, source_type)
            logger.info(
                "LinkedIn browser ingest started",
                extra={"source_type": source_type, "config": source_config_payload},
            )
            result = run_linkedin_source(source_config, source_type)
            logger.info(
                "LinkedIn browser extract completed",
                extra={
                    "source_type": source_type,
                    "result": collection_result_payload_for_logging(result),
                },
            )

            logger.info(
                "LinkedIn browser save_to_db started",
                extra={
                    "source_type": source_type,
                    "db_path": str(db_path),
                    "job_card_count": len(result.job_cards),
                },
            )
            db_summary = persist_linkedin_job_cards(connection, result.job_cards)
            logger.info(
                "LinkedIn browser save_to_db completed",
                extra={
                    "source_type": source_type,
                    "db_path": str(db_path),
                    "db_summary": db_summary,
                },
            )

            runs.append({
                "source_type": source_type,
                "source_url": result.source_url,
                "cards_requested_total": result.cards_requested_total,
                "unique_cards_total": result.unique_cards_total,
                "title_filtered_total": result.title_filtered_total,
                "title_filtered_titles": result.title_filtered_titles,
                "duplicates_skipped_total": result.duplicates_skipped_total,
                "stopped_reason": result.stopped_reason,
                "db_path": str(db_path),
                "db_summary": db_summary,
                "log_path": str(log_paths["latest"]) if log_paths else None,
            })
    finally:
        connection.close()

    return {"runs": runs}


def main() -> None:
    print(json.dumps(run_source(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
