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
    load_linkedin_email_connection_config,
    load_sqlite_config,
)
from app.sources.linkedin.alerts import fetch_linkedin_job_alert_emails
from app.sources.linkedin.log_payloads import email_fetch_result_payload_for_logging
from app.services.storage import connect_sqlite, initialize_schema, persist_linkedin_job_cards, resolve_db_path


ROOT = APP_ROOT


def run_source_email() -> dict[str, object]:
    log_paths = get_active_log_paths() or setup_logging("linkedin_email_source")
    logger = logging.getLogger(__name__)

    config = load_linkedin_email_connection_config()
    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(ROOT, sqlite_config)
    logger.info("LinkedIn email ingest started")
    logger.info(
        "LinkedIn email source config",
        extra={
            "config": {
                "provider": config.provider,
                "host": config.host,
                "port": config.port,
                "mailbox": config.mailbox,
                "username": config.username,
                "password_env": config.password_env,
                "sender": config.sender,
                "lookback_days": config.lookback_days,
                "max_messages": config.max_messages,
                "title_exclude_contains": config.title_exclude_contains,
            }
        },
    )
    logger.info("LinkedIn email storage config", extra={"storage": {"db_path": str(db_path)}})
    result = fetch_linkedin_job_alert_emails(config)
    logged_result = email_fetch_result_payload_for_logging(result)
    logger.info(
        "LinkedIn email extract completed",
        extra={"result": logged_result},
    )
    logger.info(
        "LinkedIn email save_to_db started",
        extra={"db_path": str(db_path), "job_card_count": len(result.job_cards)},
    )
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        db_summary = persist_linkedin_job_cards(connection, result.job_cards)
    finally:
        connection.close()
    logger.info(
        "LinkedIn email save_to_db completed",
        extra={"db_path": str(db_path), "db_summary": db_summary},
    )
    logger.info("LinkedIn email source completed")

    return {
        "success": result.success,
        "provider": result.provider,
        "host": result.host,
        "port": result.port,
        "mailbox": result.mailbox,
        "username": result.username,
        "sender": result.sender,
        "matched_message_count": result.matched_message_count,
        "job_card_count": len(result.job_cards),
        "error": result.error,
        "db_path": str(db_path),
        "db_summary": db_summary,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def main() -> None:
    print(json.dumps(run_source_email(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
