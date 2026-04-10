from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

from app.models import (
    LinkedInJobRankingResult,
    LinkedInRankingLabeledReason,
    LinkedInRankingConfig,
)
from app.services.llm.config import RankingLLMConfig
from app.services.storage.db import SQLiteConfig, connect_sqlite, initialize_schema


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "screening"
    / "ranking.py"
)


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("linkedin_run_ranking_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_ranking_inserts_job_rankings(tmp_path: Path, monkeypatch, capsys) -> None:
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
                "$140,000-$170,000 CAD",
                "Build applied AI systems with Python and LLMs.",
                0,
                "enriched",
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
        "load_ranking_llm_config",
        lambda: RankingLLMConfig(model="gpt-5-mini", batch_size=3, max_batches_per_run=1),
    )
    monkeypatch.setattr(
        runner_script,
        "load_linkedin_ranking_config",
        lambda: LinkedInRankingConfig.model_validate(
            {
                "profile_version": "v1",
                "target": {
                    "preferred_roles": ["Applied AI Engineer"],
                    "acceptable_roles": ["Software Engineer with explicit AI/ML cue"],
                    "preferred_work_styles": ["agent_system_building"],
                    "acceptable_work_styles": ["pure_research"],
                },
                "candidate_profile": {
                    "seniority_preference": {
                        "preferred": ["entry", "junior"],
                        "acceptable": ["mid"],
                        "avoid": ["senior"],
                    },
                    "strengths": ["Python", "LLM applications"],
                    "tech_familiarity": ["PyTorch"],
                    "weaker_areas": ["very senior production ownership"],
                },
                "preferences": {
                    "preferred": {"work_mode": ["remote"], "employment_type": ["full-time"]},
                    "acceptable": {"work_mode": ["hybrid_toronto"], "employment_type": ["contract"]},
                    "lower_preference_signals": ["very busy environment"],
                },
            }
        ),
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
        "rank_linkedin_jobs",
        lambda llm_config, ranking_config, jobs: [
            LinkedInJobRankingResult(
                linkedin_job_id=jobs[0]["linkedin_job_id"],
                role_match=LinkedInRankingLabeledReason(label="strong", reason="Strong role match"),
                level_match=LinkedInRankingLabeledReason(label="stretch", reason="Some seniority stretch"),
                preference_match=LinkedInRankingLabeledReason(label="acceptable", reason="Acceptable work mode"),
                not_applicable_reason=None,
                recommendation="apply_auto",
                summary="Strong fit with slight experience stretch.",
            )
        ],
    )

    runner_script.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["success"] is True
    assert stdout_payload["status"] == "completed"
    assert stdout_payload["candidate_count"] == 1
    assert stdout_payload["ranking_count"] == 1
    assert stdout_payload["batch_count"] == 1
    assert stdout_payload["stopped_reason"] == "max_batches_per_run_reached"
    assert stdout_payload["db_summary"]["rankings_inserted"] == 1
    assert stdout_payload["db_summary"]["jobs_marked_not_applicable"] == 0

    verify = sqlite3.connect(db_path)
    try:
        row = verify.execute(
            """
            SELECT role_match_label, level_match_label, preference_match_label, recommendation, summary
            FROM job_rankings WHERE linkedin_job_id = ?
            """,
            ("123",),
        ).fetchone()
    finally:
        verify.close()

    assert row == (
        "strong",
        "stretch",
        "acceptable",
        "apply_auto",
        "Strong fit with slight experience stretch.",
    )
