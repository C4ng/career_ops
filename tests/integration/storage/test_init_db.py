from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.services.storage.db import SQLiteConfig


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "storage"
    / "init_db.py"
)


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("storage_init_db_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_init_db_prints_db_path(tmp_path: Path, monkeypatch, capsys) -> None:
    runner_script = _load_runner_module()
    db_path = tmp_path / "data" / "job_finding.sqlite3"
    logs_path = tmp_path / "data" / "logs"

    monkeypatch.setattr(runner_script, "ROOT", tmp_path)
    monkeypatch.setattr(runner_script, "load_sqlite_config", lambda: SQLiteConfig(db_path="data/job_finding.sqlite3"))
    monkeypatch.setattr(
        runner_script,
        "setup_logging",
        lambda name: {
            "latest": logs_path / f"{name}.latest.log",
            "history": logs_path / f"{name}.history.log",
        },
    )

    runner_script.main()

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["success"] is True
    assert stdout_payload["db_path"] == str(db_path)
    assert stdout_payload["log_path"].endswith("storage_init.latest.log")
    assert db_path.exists()
