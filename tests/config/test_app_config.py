from __future__ import annotations

import logging
from pathlib import Path

import pytest
import app.settings as settings_module
from app.models import (
    LinkedInRankingConfig,
    LinkedInSourceConfig,
    LinkedInTitleTriageConfig,
)
from app.services.llm.config import (
    JDEnrichmentLLMConfig,
    RankingLLMConfig,
    TitleTriageLLMConfig,
)
from app.services.storage.db import SQLiteConfig
from pydantic import ValidationError


def test_load_linkedin_source_config_reads_common_and_keyword_search_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "logging:",
                '  level: "DEBUG"',
                "system:",
                "  linkedin:",
                "    connection:",
                '      cdp_url: "http://127.0.0.1:9222"',
                "    collection:",
                "      max_offsets: 6",
                "      keyword_search_page_step: 25",
                "      recommended_feed_page_step: 24",
                "user:",
                "  linkedin:",
                "    sources:",
                "      source_type:",
                '        - "keyword_search"',
                "      title_exclude_contains:",
                '        - "senior"',
                "      collect_limit: 30",
                "      keyword_search:",
                '        keywords: "AI Engineer"',
                '        location: "Toronto, Ontario, Canada"',
                '        posted_window: "past_week"',
                "        experience_levels:",
                '          - "entry"',
                "        start: 25",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    config = settings_module.load_linkedin_source_config()

    assert isinstance(config, LinkedInSourceConfig)
    assert config.source_type == ["keyword_search"]
    assert config.cdp_url == "http://127.0.0.1:9222"
    assert config.title_exclude_contains == ["senior"]
    assert config.collect_limit == 30
    assert config.max_offsets == 6
    assert config.keyword_search_page_step == 25
    assert config.recommended_feed_page_step == 24
    assert config.keyword_search is not None
    assert config.keyword_search.keywords == "AI Engineer"
    assert config.keyword_search.location == "Toronto, Ontario, Canada"
    assert config.keyword_search.experience_levels == ["entry"]
    assert config.keyword_search.start == 25


def test_load_logging_config_reads_logging_fields(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "logging:",
                '  level: "DEBUG"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    logging_config = settings_module.load_logging_config()

    assert logging_config.level == "DEBUG"


def test_load_sqlite_config_reads_storage_fields(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "system:",
                "  storage:",
                "    sqlite:",
                '      db_path: "data/test.sqlite3"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    sqlite_config = settings_module.load_sqlite_config()

    assert isinstance(sqlite_config, SQLiteConfig)
    assert sqlite_config.db_path == "data/test.sqlite3"


def test_load_title_triage_llm_config_reads_system_fields(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "system:",
                "  llm:",
                "    title_triage:",
                '      provider: "gemini"',
                '      model: "gemini-2.5-flash"',
                "      temperature: 0.0",
                "      batch_size: 20",
                '      prompt_version: "v1"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    config = settings_module.load_title_triage_llm_config()

    assert isinstance(config, TitleTriageLLMConfig)
    assert config.provider == "gemini"
    assert config.api_base == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert config.api_key_env == "GEMINI_API_KEY"
    assert config.model == "gemini-2.5-flash"
    assert config.temperature == 0.0
    assert config.batch_size == 20
    assert config.prompt_version == "v1"
    assert config.timeout_seconds == 60.0


def test_load_jd_enrichment_llm_config_reads_system_fields(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "system:",
                "  llm:",
                "    jd_enrichment:",
                '      provider: "gemini"',
                '      api_key_env: "GOOGLE_API_KEY"',
                '      model: "gemini-2.5-flash"',
                "      temperature: 0.0",
                "      batch_size: 15",
                '      prompt_version: "v2"',
                "      timeout_seconds: 90.0",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    config = settings_module.load_jd_enrichment_llm_config()

    assert isinstance(config, JDEnrichmentLLMConfig)
    assert config.provider == "gemini"
    assert config.api_base == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert config.api_key_env == "GOOGLE_API_KEY"
    assert config.model == "gemini-2.5-flash"
    assert config.temperature == 0.0
    assert config.batch_size == 15
    assert config.max_batches_per_run == 1
    assert config.prompt_version == "v2"
    assert config.timeout_seconds == 90.0


def test_load_ranking_llm_config_reads_system_fields(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "system:",
                "  llm:",
                "    ranking:",
                '      provider: "gemini"',
                '      api_key_env: "GOOGLE_API_KEY"',
                '      model: "gemini-2.5-flash"',
                "      temperature: 0.0",
                "      batch_size: 3",
                "      max_batches_per_run: 1",
                '      prompt_version: "v1"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    config = settings_module.load_ranking_llm_config()

    assert isinstance(config, RankingLLMConfig)
    assert config.provider == "gemini"
    assert config.api_base == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert config.api_key_env == "GOOGLE_API_KEY"
    assert config.model == "gemini-2.5-flash"
    assert config.batch_size == 3
    assert config.max_batches_per_run == 1
    assert config.prompt_version == "v1"


def test_load_linkedin_email_connection_config_reads_system_and_user_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "logging:",
                '  level: "INFO"',
                "system:",
                "  linkedin:",
                "    email:",
                '      provider: "imap"',
                '      host: "imap.gmail.com"',
                "      port: 993",
                '      mailbox: "INBOX"',
                "user:",
                "  linkedin:",
                "    sources:",
                "      title_exclude_contains:",
                '        - "senior"',
                "    email_notifications:",
                '      username: "person@example.com"',
                '      password_env: "LINKEDIN_EMAIL_APP_PASSWORD"',
                '      sender: "jobalerts-noreply@linkedin.com"',
                "      lookback_days: 14",
                "      max_messages: 50",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    config = settings_module.load_linkedin_email_connection_config()

    assert config.provider == "imap"
    assert config.host == "imap.gmail.com"
    assert config.port == 993
    assert config.mailbox == "INBOX"
    assert config.username == "person@example.com"
    assert config.password_env == "LINKEDIN_EMAIL_APP_PASSWORD"
    assert config.sender == "jobalerts-noreply@linkedin.com"
    assert config.lookback_days == 14
    assert config.max_messages == 50
    assert config.title_exclude_contains == ["senior"]


def test_load_linkedin_title_triage_config_reads_user_fields(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "user:",
                "  linkedin:",
                "    title_triage:",
                '      goal: "Triage LinkedIn titles."',
                "      role_intent:",
                '        applied_ai_engineering: "Build AI systems in products."',
                '        research_and_modeling: "Work on models, inference, and research."',
                "      wanted_roles:",
                '        - "Machine Learning Engineer"',
                '        - "Research Engineer"',
                "      wanted_technical_cues:",
                '        - "llm"',
                '        - "agent"',
                "      decision_rules:",
                '        - "Prefer keep when uncertain."',
                "      strong_keep_patterns:",
                '        - "Titles with explicit AI cues should usually be kept."',
                "      discard_patterns:",
                '        - "Discard broad software titles without AI cues."',
                "      location_policy:",
                '        - "Remote is acceptable anywhere."',
                "      important_examples:",
                "        keep:",
                '          - "Member of Technical Staff, AI Models Research"',
                "        discard:",
                '          - "Backend Engineer"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    config = settings_module.load_linkedin_title_triage_config()

    assert isinstance(config, LinkedInTitleTriageConfig)
    assert config.goal == "Triage LinkedIn titles."
    assert config.role_intent is not None
    assert config.role_intent.applied_ai_engineering == "Build AI systems in products."
    assert config.role_intent.research_and_modeling == "Work on models, inference, and research."
    assert config.wanted_roles == ["Machine Learning Engineer", "Research Engineer"]
    assert config.wanted_technical_cues == ["llm", "agent"]
    assert config.decision_rules == ["Prefer keep when uncertain."]
    assert config.strong_keep_patterns == ["Titles with explicit AI cues should usually be kept."]
    assert config.discard_patterns == ["Discard broad software titles without AI cues."]
    assert config.location_policy == ["Remote is acceptable anywhere."]
    assert config.important_examples is not None
    assert config.important_examples.keep == ["Member of Technical Staff, AI Models Research"]
    assert config.important_examples.discard == ["Backend Engineer"]


def test_load_linkedin_title_triage_config_rejects_unknown_fields(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "user:",
                "  linkedin:",
                "    title_triage:",
                '      goal: "Triage LinkedIn titles."',
                '      unexpected_field: "should fail"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    with pytest.raises(ValidationError):
        settings_module.load_linkedin_title_triage_config()


def test_load_linkedin_ranking_config_reads_user_fields(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text(
        "\n".join(
            [
                "user:",
                "  linkedin:",
                "    ranking:",
                '      profile_version: "v1"',
                "      target:",
                "        preferred_roles:",
                '          - "Applied AI Engineer"',
                "        acceptable_roles:",
                '          - "Data Scientist"',
                "        preferred_domains:",
                '          - "agent systems"',
                "        acceptable_domains:",
                '          - "robotics"',
                "        preferred_work_styles:",
                '          - "applied_ai_product"',
                "        acceptable_work_styles:",
                '          - "pure_research"',
                "      candidate_profile:",
                "        seniority_preference:",
                "          preferred:",
                '            - "entry"',
                "          acceptable:",
                '            - "mid"',
                "          avoid:",
                '            - "senior"',
                "        strengths:",
                '          - "Python"',
                "        tech_familiarity:",
                '          - "PyTorch"',
                "        weaker_areas:",
                '          - "very senior production ownership"',
                "      preferences:",
                "        preferred:",
                "          work_mode:",
                '            - "remote"',
                "          employment_type:",
                '            - "full-time"',
                "        acceptable:",
                "          work_mode:",
                '            - "hybrid_toronto"',
                "          employment_type:",
                '            - "contract"',
                "        lower_preference_signals:",
                '          - "very busy environment"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    config = settings_module.load_linkedin_ranking_config()

    assert isinstance(config, LinkedInRankingConfig)
    assert config.profile_version == "v1"
    assert config.target.preferred_roles == ["Applied AI Engineer"]
    assert config.target.preferred_domains == ["agent systems"]
    assert config.target.acceptable_domains == ["robotics"]
    assert config.candidate_profile.seniority_preference.preferred == ["entry"]
    assert config.preferences.preferred.work_mode == ["remote"]


# --- _nested_section and config file error handling (Issue #3) ---


def test_load_any_config_raises_file_not_found_with_helpful_message(tmp_path, monkeypatch) -> None:
    """Missing config file must raise FileNotFoundError with a copy-paste instruction."""
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", tmp_path / "config" / "app.yaml")

    with pytest.raises(FileNotFoundError, match="app.template.yaml"):
        settings_module.load_sqlite_config()


def test_load_config_raises_file_not_found_includes_missing_path(tmp_path, monkeypatch) -> None:
    """Error message must include the path that was not found."""
    missing = tmp_path / "config" / "app.yaml"
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", missing)

    with pytest.raises(FileNotFoundError, match=str(missing)):
        settings_module.load_logging_config()


def test_nested_section_logs_warning_when_key_missing(tmp_path, monkeypatch, caplog) -> None:
    """Missing a YAML section must emit a WARNING with the dotted config path."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    # Write a config with no system.llm section at all
    (config_dir / "app.yaml").write_text("logging:\n  level: INFO\n", encoding="utf-8")
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    with caplog.at_level(logging.WARNING, logger="app.settings"):
        settings_module.load_sqlite_config()

    # "system" key is absent — warning must name the missing path
    assert any("system" in r.config_path for r in caplog.records if hasattr(r, "config_path"))


def test_nested_section_logs_warning_when_intermediate_section_is_wrong_type(
    tmp_path, monkeypatch, caplog
) -> None:
    """If a section exists but is a scalar instead of a dict, a WARNING must be emitted."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    # system.storage is a string, not a dict
    (config_dir / "app.yaml").write_text(
        "system:\n  storage: not_a_dict\n", encoding="utf-8"
    )
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    with caplog.at_level(logging.WARNING, logger="app.settings"):
        settings_module.load_sqlite_config()

    warning = next(
        (r for r in caplog.records if "not a dict" in r.message and hasattr(r, "actual_type")),
        None,
    )
    assert warning is not None
    assert warning.actual_type == "str"


def test_nested_section_returns_empty_dict_on_missing_key(tmp_path, monkeypatch) -> None:
    """Fallback to {} still works — callers get Pydantic defaults rather than a crash."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "app.yaml").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    # SQLiteConfig has a default db_path, so this must succeed with the default
    config = settings_module.load_sqlite_config()

    assert config.db_path == "data/job_finding.sqlite3"


def test_nested_section_logs_warning_includes_full_dotted_path(tmp_path, monkeypatch, caplog) -> None:
    """The warning must identify the exact dotted path, not just the leaf key."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    # Has system but no system.llm
    (config_dir / "app.yaml").write_text("system:\n  storage:\n    sqlite:\n      db_path: x\n", encoding="utf-8")
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    monkeypatch.setattr(settings_module, "GLOBAL_CONFIG_PATH", config_dir / "app.yaml")

    with caplog.at_level(logging.WARNING, logger="app.settings"):
        settings_module.load_sqlite_config()

    # No warning expected — system.storage.sqlite IS present
    assert not any(hasattr(r, "config_path") for r in caplog.records)
