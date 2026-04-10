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
from app.sources.linkedin.log_payloads import item_examples_for_logging
from app.settings import (
    ROOT as APP_ROOT,
    load_linkedin_title_triage_config,
    load_sqlite_config,
    load_title_triage_llm_config,
)
from app.screening import triage_linkedin_job_titles
from app.services.storage import connect_sqlite, initialize_schema, resolve_db_path
from app.services.storage.title_triage import load_discovered_jobs, save_title_triage_results


ROOT = APP_ROOT


def _llm_config_for_logging(config) -> dict[str, object]:
    return {
        "provider": config.provider,
        "api_base": config.api_base,
        "api_key_env": config.api_key_env,
        "model": config.model,
        "temperature": config.temperature,
        "batch_size": config.batch_size,
        "prompt_version": config.prompt_version,
        "timeout_seconds": config.timeout_seconds,
    }


def _decision_examples_for_logging(decisions) -> list[dict[str, object]]:
    return [decision.model_dump(mode="json") for decision in decisions[:5]]


def _discarded_titles_with_reasons(decisions, candidate_by_id: dict[str, object]) -> list[dict[str, object]]:
    discarded: list[dict[str, object]] = []
    for decision in decisions:
        if decision.decision != "discard":
            continue
        candidate = candidate_by_id.get(decision.linkedin_job_id)
        discarded.append({
            "linkedin_job_id": decision.linkedin_job_id,
            "title": candidate.title if candidate is not None else None,
            "reason": decision.reason,
        })
    return discarded


def _empty_result_payload(db_path: Path, log_paths: dict[str, Path] | None) -> dict[str, object]:
    return {
        "success": True,
        "status": "no_discovered_jobs",
        "db_path": str(db_path),
        "candidate_count": 0,
        "decision_count": 0,
        "batch_count": 0,
        "db_summary": {
            "decisions_received": 0,
            "jobs_updated": 0,
            "jobs_missing": 0,
            "keep_count": 0,
            "discard_count": 0,
        },
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def run_title_triage() -> dict[str, object]:
    log_paths = get_active_log_paths() or setup_logging("linkedin_title_triage")
    logger = logging.getLogger(__name__)

    sqlite_config = load_sqlite_config()
    llm_config = load_title_triage_llm_config()
    triage_config = load_linkedin_title_triage_config()
    db_path = resolve_db_path(ROOT, sqlite_config)

    logger.info("LinkedIn title triage storage config", extra={"storage": {"db_path": str(db_path)}})
    logger.info("LinkedIn title triage LLM config", extra={"llm_config": _llm_config_for_logging(llm_config)})
    logger.info("LinkedIn title triage user config", extra={"triage_config": triage_config.model_dump(mode="json")})

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        total_candidate_count = 0
        total_decision_count = 0
        total_db_summary = {
            "decisions_received": 0,
            "jobs_updated": 0,
            "jobs_missing": 0,
            "keep_count": 0,
            "discard_count": 0,
        }
        batch_count = 0

        while True:
            logger.info(
                "LinkedIn title triage load started",
                extra={"batch_size": llm_config.batch_size, "batch_index": batch_count + 1},
            )
            candidates = load_discovered_jobs(connection, llm_config.batch_size)
            logger.info(
                "LinkedIn title triage load completed",
                extra={
                    "candidate_count": len(candidates),
                    "batch_index": batch_count + 1,
                    "candidate_examples": item_examples_for_logging(
                        candidates,
                        include_keys=["job_id", "linkedin_job_id", "title", "company", "location_text", "work_mode"],
                    ),
                },
            )
            if not candidates:
                if batch_count == 0:
                    payload = _empty_result_payload(db_path, log_paths)
                    logger.info("LinkedIn title triage completed", extra={"result": payload})
                    return payload
                break

            batch_count += 1
            total_candidate_count += len(candidates)

            logger.info(
                "LinkedIn title triage LLM call started",
                extra={"candidate_count": len(candidates), "batch_index": batch_count},
            )
            decisions = triage_linkedin_job_titles(llm_config, triage_config, candidates)
            logger.info(
                "LinkedIn title triage LLM call completed",
                extra={"decision_count": len(decisions), "batch_index": batch_count},
            )
            total_decision_count += len(decisions)

            candidate_by_id = {candidate.linkedin_job_id: candidate for candidate in candidates}
            logger.info(
                "LinkedIn title triage decision summary",
                extra={
                    "batch_index": batch_count,
                    "decision_examples": _decision_examples_for_logging(decisions),
                    "discarded_titles_with_reasons": _discarded_titles_with_reasons(decisions, candidate_by_id),
                },
            )
            logger.debug(
                "LinkedIn title triage parsed decisions",
                extra={
                    "batch_index": batch_count,
                    "decisions": [decision.model_dump(mode="json") for decision in decisions],
                },
            )

            logger.info(
                "LinkedIn title triage save_to_db started",
                extra={"decision_count": len(decisions), "batch_index": batch_count},
            )
            db_summary = save_title_triage_results(
                connection,
                decisions,
                model_name=llm_config.model,
            )
            logger.info(
                "LinkedIn title triage save_to_db completed",
                extra={
                    "db_summary": db_summary,
                    "batch_index": batch_count,
                    "db_write_preview": [
                        {
                            "linkedin_job_id": decision.linkedin_job_id,
                            "decision": decision.decision,
                            "target_stage": "triaged" if decision.decision == "keep" else "not_applicable",
                            "stage_reason": None if decision.decision == "keep" else decision.reason,
                        }
                        for decision in decisions[:5]
                    ],
                },
            )
            for key in total_db_summary:
                total_db_summary[key] += db_summary[key]
    finally:
        connection.close()

    payload = {
        "success": True,
        "status": "completed",
        "db_path": str(db_path),
        "candidate_count": total_candidate_count,
        "decision_count": total_decision_count,
        "batch_count": batch_count,
        "db_summary": total_db_summary,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }
    logger.info("LinkedIn title triage completed", extra={"result": payload})
    return payload


def main() -> None:
    print(json.dumps(run_title_triage(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
