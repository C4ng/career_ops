from __future__ import annotations

import logging
import os
from pathlib import Path

from typing import Literal

import yaml
from pydantic import BaseModel

from app.models.linkedin_config import (
    LinkedInConnectionConfig,
    LinkedInEmailConfig,
    LinkedInRankingConfig,
    LinkedInSourceConfig,
    LinkedInTitleTriageConfig,
)
from app.services.llm.config import (
    ApplicationQuestionMappingLLMConfig,
    JDEnrichmentLLMConfig,
    RankingLLMConfig,
    TitleTriageLLMConfig,
)
from app.services.storage.db import SQLiteConfig


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


ROOT = Path(__file__).resolve().parent.parent
GLOBAL_CONFIG_PATH = ROOT / "config" / "app.yaml"

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    dotenv_path = ROOT / ".env"
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            os.environ.setdefault(key, value)


def _load_global_config_payload() -> dict[str, object]:
    _load_dotenv()
    if not GLOBAL_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config file not found: {GLOBAL_CONFIG_PATH}\n"
            f"Copy config/app.template.yaml to config/app.yaml and fill in your settings."
        )
    return yaml.safe_load(GLOBAL_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _nested_section(payload: dict[str, object], *keys: str) -> dict[str, object]:
    current: object = payload
    path_so_far: list[str] = []
    for key in keys:
        path_so_far.append(key)
        if not isinstance(current, dict):
            logger.warning(
                "Config section is not a dict — falling back to empty section",
                extra={"config_path": ".".join(path_so_far), "actual_type": type(current).__name__},
            )
            return {}
        if key not in current:
            logger.warning(
                "Config section not found — falling back to empty section",
                extra={"config_path": ".".join(path_so_far)},
            )
            return {}
        current = current[key]
    if not isinstance(current, dict):
        logger.warning(
            "Config section is not a dict — falling back to empty section",
            extra={"config_path": ".".join(keys), "actual_type": type(current).__name__},
        )
        return {}
    return current


def load_linkedin_connection_config() -> LinkedInConnectionConfig:
    payload = _load_global_config_payload()
    return LinkedInConnectionConfig.model_validate(_nested_section(payload, "system", "linkedin", "connection"))


def load_logging_config() -> LoggingConfig:
    payload = _load_global_config_payload()
    return LoggingConfig.model_validate(_nested_section(payload, "logging"))


def load_sqlite_config() -> SQLiteConfig:
    payload = _load_global_config_payload()
    return SQLiteConfig.model_validate(_nested_section(payload, "system", "storage", "sqlite"))


def load_title_triage_llm_config() -> TitleTriageLLMConfig:
    payload = _load_global_config_payload()
    return TitleTriageLLMConfig.model_validate(_nested_section(payload, "system", "llm", "title_triage"))


def load_jd_enrichment_llm_config() -> JDEnrichmentLLMConfig:
    payload = _load_global_config_payload()
    return JDEnrichmentLLMConfig.model_validate(_nested_section(payload, "system", "llm", "jd_enrichment"))


def load_ranking_llm_config() -> RankingLLMConfig:
    payload = _load_global_config_payload()
    return RankingLLMConfig.model_validate(_nested_section(payload, "system", "llm", "ranking"))


def load_application_question_mapping_llm_config() -> ApplicationQuestionMappingLLMConfig:
    payload = _load_global_config_payload()
    return ApplicationQuestionMappingLLMConfig.model_validate(
        _nested_section(payload, "system", "llm", "application_question_mapping")
    )


def load_linkedin_title_triage_config() -> LinkedInTitleTriageConfig:
    payload = _load_global_config_payload()
    return LinkedInTitleTriageConfig.model_validate(_nested_section(payload, "user", "linkedin", "title_triage"))


def load_linkedin_ranking_config() -> LinkedInRankingConfig:
    payload = _load_global_config_payload()
    return LinkedInRankingConfig.model_validate(_nested_section(payload, "user", "linkedin", "ranking"))


def load_linkedin_email_connection_config() -> LinkedInEmailConfig:
    payload = _load_global_config_payload()
    system_payload = _nested_section(payload, "system", "linkedin", "email")
    user_payload = _nested_section(payload, "user", "linkedin", "email_notifications")
    source_payload = _nested_section(payload, "user", "linkedin", "sources")
    merged_payload = {
        **system_payload,
        **user_payload,
        "title_exclude_contains": source_payload.get("title_exclude_contains", []),
    }
    return LinkedInEmailConfig.model_validate(merged_payload)


def load_linkedin_source_config() -> LinkedInSourceConfig:
    payload = _load_global_config_payload()
    connection_payload = _nested_section(payload, "system", "linkedin", "connection")
    collection_payload = _nested_section(payload, "system", "linkedin", "collection")
    user_sources_payload = _nested_section(payload, "user", "linkedin", "sources")
    merged_payload = {
        "cdp_url": connection_payload.get("cdp_url"),
        **collection_payload,
        **user_sources_payload,
    }
    return LinkedInSourceConfig.model_validate(merged_payload)


__all__ = [
    "ROOT",
    "GLOBAL_CONFIG_PATH",
    "load_application_question_mapping_llm_config",
    "load_linkedin_connection_config",
    "load_linkedin_email_connection_config",
    "load_linkedin_ranking_config",
    "load_linkedin_source_config",
    "load_linkedin_title_triage_config",
    "load_jd_enrichment_llm_config",
    "load_logging_config",
    "load_ranking_llm_config",
    "load_sqlite_config",
    "load_title_triage_llm_config",
]
