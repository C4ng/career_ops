from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "pipeline.py"
)


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("linkedin_main_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_pipeline_includes_title_triage_detail_enrichment_and_ranking_steps(tmp_path: Path, monkeypatch, capsys) -> None:
    runner_script = _load_runner_module()
    logs_path = tmp_path / "data" / "logs"

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
        "run_connection",
        lambda: {"success": True, "log_path": str(logs_path / "linkedin_connection.latest.log")},
    )
    monkeypatch.setattr(
        runner_script,
        "run_source",
        lambda: {"runs": [{"source_type": "keyword_search"}]},
    )
    monkeypatch.setattr(
        runner_script,
        "run_source_email",
        lambda: {"success": True, "job_card_count": 3},
    )
    monkeypatch.setattr(
        runner_script,
        "run_title_triage",
        lambda: {"success": True, "status": "completed", "decision_count": 20},
    )
    monkeypatch.setattr(
        runner_script,
        "run_detail_fetch",
        lambda: {"success": True, "status": "completed", "detail_count": 12},
    )
    monkeypatch.setattr(
        runner_script,
        "run_jd_enrichment",
        lambda: {"success": True, "status": "completed", "enrichment_count": 8},
    )
    monkeypatch.setattr(
        runner_script,
        "run_ranking",
        lambda: {"success": True, "status": "completed", "ranking_count": 3},
    )

    runner_script.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["pipeline_status"] == "completed"
    assert stdout_payload["connection"]["success"] is True
    assert stdout_payload["browser_runs"] == [{"source_type": "keyword_search"}]
    assert stdout_payload["email_run"]["success"] is True
    assert stdout_payload["title_triage_run"]["success"] is True
    assert stdout_payload["title_triage_run"]["decision_count"] == 20
    assert stdout_payload["detail_fetch_run"]["success"] is True
    assert stdout_payload["detail_fetch_run"]["detail_count"] == 12
    assert stdout_payload["jd_enrichment_run"]["success"] is True
    assert stdout_payload["jd_enrichment_run"]["enrichment_count"] == 8
    assert stdout_payload["ranking_run"]["success"] is True
    assert stdout_payload["ranking_run"]["ranking_count"] == 3
    assert stdout_payload["log_path"].endswith("linkedin_pipeline.latest.log")
