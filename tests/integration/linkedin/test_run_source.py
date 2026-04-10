from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

from app.models import (
    LinkedInCollectionResult,
    LinkedInKeywordSearchSource,
    LinkedInSourceConfig,
)
from app.services.storage.db import SQLiteConfig


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "linkedin"
SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "source"
    / "browser.py"
)


def _load_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("linkedin_run_source_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_source_persists_keyword_search_cards_to_db(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runner_script = _load_runner_module()
    runtime_result = LinkedInCollectionResult.model_validate(
        _load_json("run_source_keyword_search_result.json")
    )

    keyword_search_config = LinkedInKeywordSearchSource(
        keywords="AI Engineer",
        location="Toronto, Ontario, Canada",
        posted_window="past_week",
        experience_levels=["internship", "entry", "mid_senior"],
        start=0,
    )
    source_config = LinkedInSourceConfig(
        source_type=["keyword_search"],
        cdp_url="http://127.0.0.1:9222",
        title_exclude_contains=["senior", "staff", "manager", "lead"],
        collect_limit=30,
        keyword_search=keyword_search_config,
    )

    logs_path = tmp_path / "data" / "logs"
    db_path = tmp_path / "data" / "job_finding.sqlite3"
    monkeypatch.setattr(runner_script, "ROOT", tmp_path)
    monkeypatch.setattr(runner_script, "load_linkedin_source_config", lambda: source_config)
    monkeypatch.setattr(runner_script, "load_sqlite_config", lambda: SQLiteConfig(db_path="data/job_finding.sqlite3"))
    monkeypatch.setattr(
        runner_script,
        "setup_logging",
        lambda name: {
            "latest": logs_path / f"{name}.latest.log",
            "history": logs_path / f"{name}.history.log",
        },
    )
    monkeypatch.setattr(
        runner_script,
        "run_linkedin_source",
        lambda config, source_type: runtime_result,
    )

    runner_script.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert len(stdout_payload["runs"]) == 1
    run = stdout_payload["runs"][0]
    assert run["source_url"].startswith("https://www.linkedin.com/jobs/search/")
    assert run["unique_cards_total"] == 2
    assert run["title_filtered_total"] == 1
    assert run["title_filtered_titles"] == ["Senior Machine Learning Engineer"]
    assert run["db_path"] == str(db_path)
    assert run["db_summary"]["cards_read"] == 2
    assert run["db_summary"]["jobs_inserted"] == 2
    assert run["db_summary"]["observations_inserted"] == 2

    connection = sqlite3.connect(db_path)
    try:
        job_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        observation_count = connection.execute("SELECT COUNT(*) FROM job_observations").fetchone()[0]
        stored_jobs = connection.execute(
            "SELECT linkedin_job_id, title, company FROM jobs ORDER BY linkedin_job_id"
        ).fetchall()
    finally:
        connection.close()

    assert job_count == 2
    assert observation_count == 2
    assert ("4389722027", "Gen AI Data Engineer", "CONFLUX SYSTEMS") in stored_jobs
