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

from app.screening import enrich_linkedin_job_descriptions
from app.sources.linkedin.log_payloads import item_examples_for_logging
from app.logging_setup import get_active_log_paths, setup_logging
from app.settings import (
    ROOT as APP_ROOT,
    load_jd_enrichment_llm_config,
    load_sqlite_config,
)
from app.services.storage import (
    connect_sqlite,
    initialize_schema,
    load_detailed_jobs_for_enrichment,
    resolve_db_path,
    save_job_enrichments,
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


def _enrichment_examples_for_logging(enrichments: list[dict[str, object]]) -> list[dict[str, object]]:
    return enrichments[:3]


def _empty_result_payload(db_path: Path, log_paths: dict[str, Path] | None) -> dict[str, object]:
    return {
        "success": True,
        "status": "no_detailed_jobs",
        "db_path": str(db_path),
        "candidate_count": 0,
        "enrichment_count": 0,
        "batch_count": 0,
        "stopped_reason": "no_detailed_jobs",
        "db_summary": {
            "enrichments_received": 0,
            "jobs_updated": 0,
            "jobs_missing": 0,
            "work_mode_saved": 0,
            "salary_text_saved": 0,
            "employment_type_saved": 0,
            "company_intro_saved": 0,
            "role_scope_saved": 0,
            "requirements_saved": 0,
            "benefits_saved": 0,
            "application_details_saved": 0,
        },
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def run_jd_enrichment() -> dict[str, object]:
    log_paths = get_active_log_paths() or setup_logging("linkedin_jd_enrichment")
    logger = logging.getLogger(__name__)

    sqlite_config = load_sqlite_config()
    llm_config = load_jd_enrichment_llm_config()
    db_path = resolve_db_path(ROOT, sqlite_config)

    logger.info("LinkedIn JD enrichment storage config", extra={"storage": {"db_path": str(db_path)}})
    logger.info("LinkedIn JD enrichment LLM config", extra={"llm_config": _llm_config_for_logging(llm_config)})

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        total_candidate_count = 0
        total_enrichment_count = 0
        total_db_summary = {
            "enrichments_received": 0,
            "jobs_updated": 0,
            "jobs_missing": 0,
            "work_mode_saved": 0,
            "salary_text_saved": 0,
            "employment_type_saved": 0,
            "company_intro_saved": 0,
            "role_scope_saved": 0,
            "requirements_saved": 0,
            "benefits_saved": 0,
            "application_details_saved": 0,
        }
        batch_count = 0
        stopped_reason = "completed_all_detailed_jobs"

        while True:
            if batch_count >= llm_config.max_batches_per_run:
                stopped_reason = "max_batches_per_run_reached"
                break
            logger.info(
                "LinkedIn JD enrichment ingest started",
                extra={"batch_size": llm_config.batch_size, "batch_index": batch_count + 1},
            )
            candidates = load_detailed_jobs_for_enrichment(connection, llm_config.batch_size)
            logger.info(
                "LinkedIn JD enrichment ingest completed",
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
                        ],
                    ),
                },
            )
            if not candidates:
                if batch_count == 0:
                    payload = _empty_result_payload(db_path, log_paths)
                    logger.info("LinkedIn JD enrichment completed", extra={"result": payload})
                    return payload
                stopped_reason = "completed_all_detailed_jobs"
                break

            batch_count += 1
            total_candidate_count += len(candidates)

            logger.info(
                "LinkedIn JD enrichment extract started",
                extra={"candidate_count": len(candidates), "batch_index": batch_count},
            )
            enrichments = enrich_linkedin_job_descriptions(llm_config, candidates)
            logger.info(
                "LinkedIn JD enrichment extract completed",
                extra={
                    "enrichment_count": len(enrichments),
                    "batch_index": batch_count,
                    "enrichment_examples": _enrichment_examples_for_logging(enrichments),
                },
            )
            logger.debug(
                "LinkedIn JD enrichment parsed enrichments",
                extra={"batch_index": batch_count, "enrichments": enrichments},
            )
            total_enrichment_count += len(enrichments)

            logger.info(
                "LinkedIn JD enrichment save_to_db started",
                extra={"enrichment_count": len(enrichments), "batch_index": batch_count},
            )
            db_summary = save_job_enrichments(connection, enrichments)
            logger.info(
                "LinkedIn JD enrichment save_to_db completed",
                extra={
                    "db_summary": db_summary,
                    "batch_index": batch_count,
                    "db_write_preview": [
                        {
                            "linkedin_job_id": enrichment["linkedin_job_id"],
                            "target_stage": "enriched",
                            "work_mode": enrichment.get("work_mode"),
                            "employment_type": enrichment.get("employment_type"),
                            "salary_text": enrichment.get("salary_text"),
                            "company_intro_count": len(enrichment.get("company_intro") or []),
                            "role_scope_count": len(enrichment.get("role_scope") or []),
                            "benefits_count": len(enrichment.get("benefits") or []),
                            "application_details_count": len(enrichment.get("application_details") or []),
                        }
                        for enrichment in enrichments[:5]
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
        "enrichment_count": total_enrichment_count,
        "batch_count": batch_count,
        "stopped_reason": stopped_reason,
        "db_summary": total_db_summary,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }
    logger.info("LinkedIn JD enrichment completed", extra={"result": payload})
    return payload


def main() -> None:
    print(json.dumps(run_jd_enrichment(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
