from __future__ import annotations

import json
import logging

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.logging_setup import get_active_log_paths, setup_logging
from app.settings import load_linkedin_connection_config
from app.services.browser import verify_linkedin_connection


def run_connection() -> dict[str, object]:
    log_paths = get_active_log_paths() or setup_logging("linkedin_connection")
    logger = logging.getLogger(__name__)

    config = load_linkedin_connection_config()
    logger.info("Running LinkedIn connection check")
    logger.info("LinkedIn connection config", extra={"config": config.model_dump(mode="json")})
    result = verify_linkedin_connection(config)
    logger.info("LinkedIn connection result", extra={"result": result.model_dump(mode="json")})

    return {
        "success": result.success,
        "current_url": result.current_url,
        "page_title": result.page_title,
        "error": result.error,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def main() -> None:
    print(json.dumps(run_connection(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
