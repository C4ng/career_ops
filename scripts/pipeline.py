from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    _HERE = Path(__file__).resolve()
    _REPO_ROOT = next((parent for parent in _HERE.parents if (parent / "pyproject.toml").exists()), _HERE.parents[1])
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.logging_setup import setup_logging
from scripts.connection.browser import run_connection
from scripts.screening.detail_fetch import run_detail_fetch
from scripts.screening.jd_enrichment import run_jd_enrichment
from scripts.screening.ranking import run_ranking
from scripts.source.browser import run_source
from scripts.source.email import run_source_email
from scripts.screening.title_triage import run_title_triage


def run_pipeline() -> dict[str, object]:
    log_paths = setup_logging("linkedin_pipeline")
    logger = logging.getLogger(__name__)
    logger.info("Starting LinkedIn pipeline")

    logger.info("LinkedIn pipeline stage started", extra={"stage": "connection_check"})
    connection = run_connection()
    browser_source_payload = {"runs": []}
    if connection.get("success"):
        logger.info("LinkedIn pipeline stage started", extra={"stage": "browser_sources"})
        browser_source_payload = run_source()
    else:
        logger.error("LinkedIn browser stage skipped after connection failure", extra={"connection": connection})

    logger.info("LinkedIn pipeline stage started", extra={"stage": "email_source"})
    email_source_payload = run_source_email()

    logger.info("LinkedIn pipeline stage started", extra={"stage": "title_triage"})
    title_triage_payload = run_title_triage()

    browser_success = connection.get("success", False)
    if browser_success:
        logger.info("LinkedIn pipeline stage started", extra={"stage": "detail_fetch"})
        detail_fetch_payload = run_detail_fetch()
    else:
        detail_fetch_payload = {
            "success": False,
            "status": "skipped_after_connection_failure",
        }
        logger.error(
            "LinkedIn detail fetch stage skipped after connection failure",
            extra={"connection": connection},
        )

    logger.info("LinkedIn pipeline stage started", extra={"stage": "jd_enrichment"})
    jd_enrichment_payload = run_jd_enrichment()

    logger.info("LinkedIn pipeline stage started", extra={"stage": "ranking"})
    ranking_payload = run_ranking()

    email_success = email_source_payload.get("success", False)
    triage_success = title_triage_payload.get("success", False)
    detail_fetch_success = detail_fetch_payload.get("success", False)
    jd_enrichment_success = jd_enrichment_payload.get("success", False)
    ranking_success = ranking_payload.get("success", False)

    if (
        browser_success
        and email_success
        and triage_success
        and detail_fetch_success
        and jd_enrichment_success
        and ranking_success
    ):
        pipeline_status = "completed"
    elif (
        browser_success
        or email_success
        or triage_success
        or detail_fetch_success
        or jd_enrichment_success
        or ranking_success
    ):
        pipeline_status = "completed_with_partial_failure"
    else:
        pipeline_status = "failed"

    payload = {
        "pipeline_status": pipeline_status,
        "connection": connection,
        "browser_runs": browser_source_payload.get("runs", []),
        "email_run": email_source_payload,
        "title_triage_run": title_triage_payload,
        "detail_fetch_run": detail_fetch_payload,
        "jd_enrichment_run": jd_enrichment_payload,
        "ranking_run": ranking_payload,
        "log_path": str(log_paths["latest"]),
    }
    logger.info("LinkedIn pipeline result", extra={"result": payload})
    logger.info(
        "LinkedIn pipeline completed",
        extra={
            "browser_runs": len(payload["browser_runs"]),
            "email_success": email_success,
            "title_triage_success": triage_success,
            "detail_fetch_success": detail_fetch_success,
            "jd_enrichment_success": jd_enrichment_success,
            "ranking_success": ranking_success,
            "pipeline_status": pipeline_status,
        },
    )
    return payload


def main() -> None:
    print(json.dumps(run_pipeline(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
