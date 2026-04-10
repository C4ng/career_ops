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

from app.screening import rank_linkedin_jobs
from app.sources.linkedin.log_payloads import item_examples_for_logging
from app.logging_setup import get_active_log_paths, setup_logging
from app.settings import (
    ROOT as APP_ROOT,
    load_linkedin_ranking_config,
    load_ranking_llm_config,
    load_sqlite_config,
)
from app.services.storage import (
    connect_sqlite,
    initialize_schema,
    load_enriched_jobs_for_ranking,
    resolve_db_path,
    save_job_rankings,
)


ROOT = APP_ROOT


def _llm_config_for_logging(config) -> dict[str, object]:
    return {
        "provider": config.provider,
        "api_base": config.api_base,
        "api_key_env": config.api_key_env,
        "model": config.model,
        "temperature": config.temperature,
        "batch_size": config.batch_size,
        "max_batches_per_run": config.max_batches_per_run,
        "prompt_version": config.prompt_version,
        "timeout_seconds": config.timeout_seconds,
    }


def _ranking_examples_for_logging(rankings) -> list[dict[str, object]]:
    return [ranking.model_dump(mode="json") for ranking in rankings[:5]]


def _empty_result_payload(db_path: Path, log_paths: dict[str, Path] | None) -> dict[str, object]:
    return {
        "success": True,
        "status": "no_enriched_jobs",
        "db_path": str(db_path),
        "candidate_count": 0,
        "ranking_count": 0,
        "batch_count": 0,
        "stopped_reason": "no_enriched_jobs",
        "db_summary": {
            "rankings_received": 0,
            "rankings_inserted": 0,
            "jobs_missing": 0,
            "jobs_marked_not_applicable": 0,
            "apply_focus_count": 0,
            "apply_auto_count": 0,
            "low_priority_count": 0,
        },
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def run_ranking() -> dict[str, object]:
    log_paths = get_active_log_paths() or setup_logging("linkedin_ranking")
    logger = logging.getLogger(__name__)

    sqlite_config = load_sqlite_config()
    llm_config = load_ranking_llm_config()
    ranking_config = load_linkedin_ranking_config()
    db_path = resolve_db_path(ROOT, sqlite_config)

    logger.info("LinkedIn ranking storage config", extra={"storage": {"db_path": str(db_path)}})
    logger.info("LinkedIn ranking LLM config", extra={"llm_config": _llm_config_for_logging(llm_config)})
    logger.info("LinkedIn ranking user config", extra={"ranking_config": ranking_config.model_dump(mode="json")})

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        total_candidate_count = 0
        total_ranking_count = 0
        total_db_summary = {
            "rankings_received": 0,
            "rankings_inserted": 0,
            "jobs_missing": 0,
            "jobs_marked_not_applicable": 0,
            "apply_focus_count": 0,
            "apply_auto_count": 0,
            "low_priority_count": 0,
        }
        batch_count = 0
        stopped_reason = "completed_all_enriched_jobs"

        while True:
            if batch_count >= llm_config.max_batches_per_run:
                stopped_reason = "max_batches_per_run_reached"
                break
            logger.info(
                "LinkedIn ranking ingest started",
                extra={"batch_size": llm_config.batch_size, "batch_index": batch_count + 1},
            )
            candidates = load_enriched_jobs_for_ranking(
                connection,
                llm_config.batch_size,
                prompt_version=llm_config.prompt_version,
                profile_version=ranking_config.profile_version,
            )
            logger.info(
                "LinkedIn ranking ingest completed",
                extra={
                    "candidate_count": len(candidates),
                    "batch_index": batch_count + 1,
                    "candidate_examples": item_examples_for_logging(
                        candidates,
                        include_keys=[
                            "job_id",
                            "linkedin_job_id",
                            "title",
                            "company",
                            "easy_apply",
                            "work_mode",
                            "employment_type",
                            "salary_text",
                        ],
                    ),
                },
            )
            if not candidates:
                if batch_count == 0:
                    payload = _empty_result_payload(db_path, log_paths)
                    logger.info("LinkedIn ranking completed", extra={"result": payload})
                    return payload
                stopped_reason = "completed_all_enriched_jobs"
                break

            batch_count += 1
            total_candidate_count += len(candidates)

            logger.info(
                "LinkedIn ranking extract started",
                extra={"candidate_count": len(candidates), "batch_index": batch_count},
            )
            rankings = rank_linkedin_jobs(llm_config, ranking_config, candidates)
            logger.info(
                "LinkedIn ranking extract completed",
                extra={
                    "ranking_count": len(rankings),
                    "batch_index": batch_count,
                    "ranking_examples": _ranking_examples_for_logging(rankings),
                },
            )
            logger.debug(
                "LinkedIn ranking parsed rankings",
                extra={
                    "batch_index": batch_count,
                    "rankings": [ranking.model_dump(mode="json") for ranking in rankings],
                },
            )
            total_ranking_count += len(rankings)

            logger.info(
                "LinkedIn ranking save_to_db started",
                extra={"ranking_count": len(rankings), "batch_index": batch_count},
            )
            db_summary = save_job_rankings(
                connection,
                rankings,
                model_name=llm_config.model,
                prompt_version=llm_config.prompt_version,
                profile_version=ranking_config.profile_version,
            )
            logger.info(
                "LinkedIn ranking save_to_db completed",
                extra={
                    "db_summary": db_summary,
                    "batch_index": batch_count,
                    "db_write_preview": [
                        {
                            "linkedin_job_id": ranking.linkedin_job_id,
                            "recommendation": ranking.recommendation,
                            "target_stage": "not_applicable" if ranking.not_applicable_reason else "enriched",
                            "not_applicable_reason": ranking.not_applicable_reason,
                            "role_match": ranking.role_match.label,
                            "level_match": ranking.level_match.label,
                            "preference_match": ranking.preference_match.label,
                        }
                        for ranking in rankings[:5]
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
        "ranking_count": total_ranking_count,
        "batch_count": batch_count,
        "stopped_reason": stopped_reason,
        "db_summary": total_db_summary,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }
    logger.info("LinkedIn ranking completed", extra={"result": payload})
    return payload


def main() -> None:
    print(json.dumps(run_ranking(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
