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
from app.settings import load_linkedin_email_connection_config
from app.sources.linkedin.alerts import verify_linkedin_email_connection


def run_connection_email() -> dict[str, object]:
    log_paths = get_active_log_paths() or setup_logging("linkedin_email_connection")
    logger = logging.getLogger(__name__)

    config = load_linkedin_email_connection_config()
    logger.info("Running LinkedIn email connection check")
    logger.info(
        "LinkedIn email connection config",
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
            }
        },
    )
    result = verify_linkedin_email_connection(config)
    logger.info("LinkedIn email connection check completed")

    return {
        "success": result.success,
        "provider": result.provider,
        "host": result.host,
        "port": result.port,
        "mailbox": result.mailbox,
        "username": result.username,
        "authenticated": result.authenticated,
        "mailbox_selected": result.mailbox_selected,
        "error": result.error,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def main() -> None:
    print(json.dumps(run_connection_email(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
