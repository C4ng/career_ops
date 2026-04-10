from __future__ import annotations

import argparse
import json
import logging

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.sources.linkedin.alerts import fetch_linkedin_application_confirmation_emails
from app.logging_setup import get_active_log_paths, setup_logging
from app.settings import (
    ROOT as APP_ROOT,
    load_linkedin_email_connection_config,
    load_sqlite_config,
)
from app.services.storage import (
    process_confirmation_emails,
    connect_sqlite,
    initialize_schema,
    resolve_db_path,
)


ROOT = APP_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch LinkedIn application confirmation emails and mark matching jobs as applied."
    )
    parser.add_argument(
        "--sender",
        default="jobs-noreply@linkedin.com",
        help="Email sender used for LinkedIn application confirmations.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Override the configured mailbox lookback window.",
    )
    parser.add_argument(
        "--application-type",
        default="external_apply",
        help="Application type to confirm from email. linkedin_easy_apply is intentionally disabled.",
    )
    return parser.parse_args()


def run_application_confirmation_email(
    *,
    sender: str = "jobs-noreply@linkedin.com",
    lookback_days: int | None = None,
    application_type: str = "external_apply",
) -> dict[str, object]:
    log_paths = get_active_log_paths() or setup_logging(
        "linkedin_application_confirmation_email"
    )
    logger = logging.getLogger(__name__)

    config = load_linkedin_email_connection_config()
    config.sender = sender
    if lookback_days is not None:
        config.lookback_days = lookback_days

    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(ROOT, sqlite_config)

    logger.info(
        "LinkedIn application confirmation email ingest started",
        extra={
            "config": {
                "provider": config.provider,
                "host": config.host,
                "port": config.port,
                "mailbox": config.mailbox,
                "username": config.username,
                "sender": config.sender,
                "lookback_days": config.lookback_days,
                "max_messages": config.max_messages,
            }
        },
    )

    result = fetch_linkedin_application_confirmation_emails(config)
    logger.info(
        "LinkedIn application confirmation extract completed",
        extra={
            "result": {
                "success": result.success,
                "matched_message_count": result.matched_message_count,
                "confirmation_count": len(result.confirmations),
                "error": result.error,
                "confirmations": [item.model_dump(mode="json") for item in result.confirmations[:10]],
            }
        },
    )

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        summary = process_confirmation_emails(
            connection,
            result.confirmations,
            application_type=application_type,
        )
    finally:
        connection.close()
    logger.info(
        "LinkedIn application confirmation save_to_db completed",
        extra={"db_path": str(db_path), "db_summary": summary},
    )

    return {
        "success": result.success,
        "sender": config.sender,
        "matched_message_count": result.matched_message_count,
        "confirmation_count": len(result.confirmations),
        "error": result.error,
        "db_path": str(db_path),
        "db_summary": summary,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            run_application_confirmation_email(
                sender=args.sender,
                lookback_days=args.lookback_days,
                application_type=args.application_type,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
