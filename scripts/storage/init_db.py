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
from app.settings import ROOT as APP_ROOT, load_sqlite_config
from app.services.storage.db import connect_sqlite, initialize_schema, resolve_db_path


ROOT = APP_ROOT


def init_db() -> dict[str, object]:
    log_paths = get_active_log_paths() or setup_logging("storage_init")
    logger = logging.getLogger(__name__)

    config = load_sqlite_config()
    db_path = resolve_db_path(ROOT, config)
    logger.info("Initializing SQLite storage", extra={"config": {"db_path": config.db_path, "resolved_db_path": str(db_path)}})

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
    finally:
        connection.close()

    logger.info("SQLite storage initialized", extra={"db_path": str(db_path)})
    return {
        "success": True,
        "db_path": str(db_path),
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def main() -> None:
    print(json.dumps(init_db(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
