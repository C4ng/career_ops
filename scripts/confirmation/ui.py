from __future__ import annotations

import argparse
import json
import logging

from playwright.sync_api import sync_playwright

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.models import DEFAULT_CDP_URL
from app.application.confirmation import verify_submitted_applications_in_linkedin_ui
from app.logging_setup import setup_logging
from app.settings import load_sqlite_config
from app.services.storage import (
    connect_sqlite,
    initialize_schema,
    load_submitted_pending_applications,
    mark_job_as_applied_from_confirmation,
    resolve_db_path,
)
from app.services.storage._shared import now_iso


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify submitted_pending_confirmation applications against LinkedIn UI."
    )
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help="Chrome DevTools Protocol URL for the logged-in browser session.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum submitted_pending_confirmation applications to inspect.",
    )
    return parser.parse_args()


def run_application_confirmation_ui(
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    limit: int = 20,
) -> dict[str, object]:
    log_paths = setup_logging("linkedin_application_confirmation_ui")
    logger = logging.getLogger(__name__)

    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(REPO_ROOT, sqlite_config)
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        candidates = load_submitted_pending_applications(connection, limit)
    finally:
        connection.close()

    logger.info(
        "LinkedIn UI confirmation verification started",
        extra={
            "candidate_count": len(candidates),
            "limit": limit,
            "cdp_url": cdp_url,
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        confirmations = verify_submitted_applications_in_linkedin_ui(browser, candidates)

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        updates: list[dict[str, object]] = []
        verified_at = now_iso()
        for item in confirmations:
            if not item["confirmed"]:
                updates.append(item)
                continue
            summary = mark_job_as_applied_from_confirmation(
                connection,
                linkedin_job_id=str(item["linkedin_job_id"]),
                applied_at=verified_at,
                confirmation_source=str(item["source_type"]),
                last_seen_url=str(item.get("matched_page_url") or item.get("job_url") or ""),
            )
            updates.append({**item, **summary})
    finally:
        connection.close()

    summary = {
        "candidates_checked": len(candidates),
        "confirmed_count": sum(1 for item in updates if item.get("confirmed")),
        "jobs_updated": sum(1 for item in updates if item.get("job_updated")),
        "updates": updates,
    }
    logger.info(
        "LinkedIn UI confirmation verification completed",
        extra={"db_path": str(db_path), "summary": summary},
    )
    return {
        "success": True,
        "db_path": str(db_path),
        "summary": summary,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            run_application_confirmation_ui(
                cdp_url=args.cdp_url,
                limit=args.limit,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
