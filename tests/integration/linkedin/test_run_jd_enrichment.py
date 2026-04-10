from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

from app.services.llm.config import JDEnrichmentLLMConfig
from app.services.storage.db import SQLiteConfig, connect_sqlite, initialize_schema


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "screening"
    / "jd_enrichment.py"
)


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("linkedin_run_jd_enrichment_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_jd_enrichment_updates_job_rows(tmp_path: Path, monkeypatch, capsys) -> None:
    runner_script = _load_runner_module()
    db_path = tmp_path / "data" / "job_finding.sqlite3"
    logs_path = tmp_path / "data" / "logs"

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        connection.execute(
            """
            INSERT INTO jobs (
                linkedin_job_id, job_url, title, company, location_text, work_mode, salary_text,
                job_description, easy_apply, stage, stage_reason, stage_updated_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "123",
                "https://www.linkedin.com/jobs/view/123/",
                "AI Engineer",
                "Example",
                "Toronto, ON",
                "hybrid",
                None,
                "Build applied AI systems with Python and LLMs.",
                0,
                "detailed",
                None,
                "2026-03-27T00:00:00Z",
                "2026-03-27T00:00:00Z",
                "2026-03-27T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(runner_script, "ROOT", tmp_path)
    monkeypatch.setattr(runner_script, "load_sqlite_config", lambda: SQLiteConfig(db_path="data/job_finding.sqlite3"))
    monkeypatch.setattr(
        runner_script,
        "load_jd_enrichment_llm_config",
        lambda: JDEnrichmentLLMConfig(model="gpt-5-mini", batch_size=5, max_batches_per_run=1),
    )
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
        "enrich_linkedin_job_descriptions",
        lambda llm_config, jobs: [
            {
                "linkedin_job_id": jobs[0]["linkedin_job_id"],
                "work_mode": "hybrid",
                "salary_text": "$140,000-$170,000 CAD",
                "employment_type": "Full-time",
                "company_intro": ["AI company"],
                "role_scope": ["Build applied AI systems"],
                "requirements": {
                    "summary": ["Applied AI role"],
                    "skills": ["Python", "LLMs"],
                    "experience": ["Production software experience"],
                    "tech": ["PyTorch"],
                    "education": [],
                    "constraints": [],
                    "other": [],
                },
                "benefits": ["Flexible work"],
                "application_details": ["Applications reviewed on a rolling basis"],
            }
        ],
    )

    runner_script.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["success"] is True
    assert stdout_payload["status"] == "completed"
    assert stdout_payload["candidate_count"] == 1
    assert stdout_payload["enrichment_count"] == 1
    assert stdout_payload["batch_count"] == 1
    assert stdout_payload["stopped_reason"] == "max_batches_per_run_reached"
    assert stdout_payload["db_summary"]["jobs_updated"] == 1

    verify = sqlite3.connect(db_path)
    try:
        row = verify.execute(
            """
            SELECT work_mode, salary_text, employment_type, company_intro, role_scope, requirements, benefits, application_details, stage, stage_reason
            FROM jobs WHERE linkedin_job_id = ?
            """,
            ("123",),
        ).fetchone()
    finally:
        verify.close()

    assert row[0] == "hybrid"
    assert row[1] == "$140,000-$170,000 CAD"
    assert row[2] == "Full-time"
    assert json.loads(row[3]) == ["AI company"]
    assert json.loads(row[4]) == ["Build applied AI systems"]
    assert json.loads(row[5])["skills"] == ["Python", "LLMs"]
    assert json.loads(row[6]) == ["Flexible work"]
    assert json.loads(row[7]) == ["Applications reviewed on a rolling basis"]
    assert row[8] == "enriched"
    assert row[9] is None
