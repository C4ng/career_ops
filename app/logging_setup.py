from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import app.settings as settings_module


_STANDARD_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__.keys())

_active_log_paths: dict[str, Path] | None = None


class ExtraJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        excluded_fields = _STANDARD_LOG_RECORD_FIELDS | {"message", "asctime"}
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in excluded_fields
        }
        if not extras:
            return rendered
        pretty = json.dumps(extras, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        indented = "\n".join(f"  {line}" for line in pretty.splitlines())
        return f"{rendered}\n{indented}"


def get_active_log_paths() -> dict[str, Path] | None:
    return _active_log_paths


def setup_logging(log_name: str) -> dict[str, Path]:
    global _active_log_paths
    logs_dir = settings_module.ROOT / "data" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging_config = settings_module.load_logging_config()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    latest = logs_dir / f"{log_name}.latest.log"
    history = logs_dir / f"{log_name}.{timestamp}.log"

    formatter = ExtraJsonFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, logging_config.level))
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    for path in (latest, history):
        handler = logging.FileHandler(path, mode="w", encoding="utf-8")
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    paths = {"latest": latest, "history": history}
    _active_log_paths = paths
    return paths


__all__ = ["ExtraJsonFormatter", "get_active_log_paths", "setup_logging"]
