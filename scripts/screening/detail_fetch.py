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

from app.sources.linkedin.scraper import fetch_linkedin_job_details
from app.sources.linkedin.log_payloads import item_examples_for_logging
from app.logging_setup import get_active_log_paths, setup_logging
from app.settings import ROOT as APP_ROOT
from app.settings import load_linkedin_connection_config, load_sqlite_config
from app.services.storage import (
    connect_sqlite,
    initialize_schema,
    load_triaged_jobs_for_detail_fetch,
    resolve_db_path,
    save_job_details,
)


ROOT = APP_ROOT


def _empty_result_payload(db_path: Path, log_paths: dict[str, Path] | None) -> dict[str, object]:
    return {
        "success": True,
        "status": "no_triaged_jobs",
        "db_path": str(db_path),
        "candidate_count": 0,
        "detail_count": 0,
        "db_summary": {
            "details_received": 0,
            "jobs_updated": 0,
            "jobs_missing": 0,
            "descriptions_saved": 0,
            "descriptions_missing": 0,
            "apply_link_saved": 0,
            "posted_text_saved": 0,
            "work_mode_saved": 0,
            "employment_type_saved": 0,
            "applicant_count_saved": 0,
            "application_status_saved": 0,
        },
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def run_detail_fetch() -> dict[str, object]:
    log_paths = get_active_log_paths() or setup_logging("linkedin_detail_fetch")
    logger = logging.getLogger(__name__)

    connection_config = load_linkedin_connection_config()
    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(ROOT, sqlite_config)
    logger.info("LinkedIn detail fetch browser config", extra={"config": connection_config.model_dump(mode="json")})
    logger.info("LinkedIn detail fetch storage config", extra={"storage": {"db_path": str(db_path)}})

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)

        logger.info("LinkedIn detail fetch ingest started")
        candidates = load_triaged_jobs_for_detail_fetch(connection)
        logger.info(
            "LinkedIn detail fetch ingest completed",
            extra={
                "candidate_count": len(candidates),
                "candidate_examples": item_examples_for_logging(
                    candidates,
                    include_keys=["job_id", "linkedin_job_id", "title", "company", "location_text", "work_mode"],
                ),
            },
        )
        if not candidates:
            payload = _empty_result_payload(db_path, log_paths)
            logger.info("LinkedIn detail fetch completed", extra={"result": payload})
            return payload

        logger.info(
            "LinkedIn detail fetch extract started",
            extra={"candidate_count": len(candidates), "cdp_url": connection_config.cdp_url},
        )
        details = fetch_linkedin_job_details(connection_config.cdp_url, candidates)
        logger.info(
            "LinkedIn detail fetch extract completed",
            extra={
                "detail_count": len(details),
                "described_jobs": [
                    {
                        "linkedin_job_id": detail["linkedin_job_id"],
                        "title": detail["title"],
                        "has_job_description": bool(detail["job_description"]),
                        "job_description_length": len(detail["job_description"] or ""),
                        "observed_posted_text": detail["observed_posted_text"],
                        "work_mode": detail["work_mode"],
                        "employment_type": detail["employment_type"],
                        "applicant_count_text": detail["applicant_count_text"],
                        "application_status_text": detail["application_status_text"],
                        "easy_apply": detail["easy_apply"],
                        "apply_link": detail["apply_link"],
                    }
                    for detail in details
                ],
            },
        )

        logger.info("LinkedIn detail fetch save_to_db started", extra={"detail_count": len(details)})
        db_summary = save_job_details(connection, details)
        logger.info(
            "LinkedIn detail fetch save_to_db completed",
            extra={
                "db_summary": db_summary,
                "db_write_preview": [
                    {
                        "linkedin_job_id": detail["linkedin_job_id"],
                        "target_stage": (
                            "not_applicable"
                            if detail.get("application_status_text") == "No longer accepting applications"
                            else "detailed"
                        ),
                        "easy_apply": bool(detail.get("easy_apply")),
                        "apply_link_present": bool(detail.get("apply_link")),
                        "job_description_length": len(detail.get("job_description") or ""),
                        "application_status_text": detail.get("application_status_text"),
                    }
                    for detail in details[:5]
                ],
            },
        )
    finally:
        connection.close()

    payload = {
        "success": True,
        "status": "completed",
        "db_path": str(db_path),
        "candidate_count": len(candidates),
        "detail_count": len(details),
        "db_summary": db_summary,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }
    logger.info("LinkedIn detail fetch completed", extra={"result": payload})
    return payload


def main() -> None:
    print(json.dumps(run_detail_fetch(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
