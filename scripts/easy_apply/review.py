from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.models import DEFAULT_CDP_URL
from app.application.easy_apply.review import apply_review_overrides_in_open_modal, find_open_easy_apply_page
from app.logging_setup import setup_logging
from app.settings import load_sqlite_config
from app.services.storage import (
    connect_sqlite,
    initialize_schema,
    load_application_questions,
    load_job_application,
    update_application_question_answer,
    update_job_application_status,
)
from app.services.storage.db import resolve_db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resume an Easy Apply review session and apply human overrides.")
    parser.add_argument("--application-id", type=int, required=True)
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help="Chrome DevTools Protocol URL for the logged-in browser session.",
    )
    parser.add_argument(
        "--overrides-file",
        default=None,
        help="Optional YAML/JSON file mapping question_key to the reviewed answer.",
    )
    parser.add_argument("--submit", action="store_true", help="Click submit after returning to the final review page.")
    return parser.parse_args()


def _load_overrides(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("overrides file must be a mapping of question_key to answer value")
    return {str(key): str(value) for key, value in payload.items() if value is not None}


def run_easy_apply_review(
    *,
    application_id: int,
    cdp_url: str,
    overrides: dict[str, str],
    submit: bool,
) -> dict[str, object]:
    setup_logging("linkedin_easy_apply_review")
    logger = logging.getLogger(__name__)

    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(REPO_ROOT, sqlite_config)
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        application = load_job_application(connection, application_id)
        if application is None:
            raise ValueError(f"Application {application_id} was not found.")
        question_rows = load_application_questions(connection, application_id)
    finally:
        connection.close()

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        page = find_open_easy_apply_page(
            browser,
            linkedin_job_id=str(application["linkedin_job_id"]),
            last_seen_url=application.get("last_seen_url"),
        )
        if page is None:
            raise RuntimeError("No open Easy Apply modal matching this application was found in the connected browser.")

        result = apply_review_overrides_in_open_modal(
            page,
            question_rows=question_rows,
            overrides=overrides,
            submit=submit,
        )
        current_url = page.url
        screenshot_dir = REPO_ROOT / "data" / "reviews" / "easy_apply_review_session.latest"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"application_{application_id}.png"
        page.screenshot(path=str(screenshot_path), full_page=False)

    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        applied_keys = {
            item["question_key"]
            for item in result.get("applied_overrides", [])
            if item.get("applied")
        }
        for question_key, answer_value in overrides.items():
            if question_key not in applied_keys:
                continue
            update_application_question_answer(
                connection,
                application_id=application_id,
                question_key=question_key,
                answer_value=answer_value,
                answer_source="deterministic",
                confidence="high",
                reason="Updated during human review.",
            )
        status = "submitted_pending_confirmation" if submit and result["status"] == "submitted_clicked" else "review_ready"
        pause_reason: str | None = None
        if result.get("pending_overrides"):
            pause_reason = "Pending human review changes were not fully applied in the browser."
        elif submit and result["status"] == "submit_blocked_pending_overrides":
            pause_reason = "Submit blocked because pending review changes remain unresolved."
        elif submit and result["status"] == "submit_not_confirmed":
            pause_reason = "Submit was clicked, but no LinkedIn success signal was detected."
        update_job_application_status(
            connection,
            application_id,
            status=status,
            pause_reason=pause_reason,
            review_step_name="Review your application" if status == "review_ready" else None,
            last_seen_url=current_url,
            last_screenshot_path=str(screenshot_path),
            submitted=bool(submit and result["status"] == "submitted_clicked"),
            completed=False,
        )
    finally:
        connection.close()

    logger.info(
        "Easy Apply review session completed",
        extra={
            "application_id": application_id,
            "submit": submit,
            "override_count": len(overrides),
            "result": result,
            "current_url": current_url,
            "screenshot_path": str(screenshot_path),
        },
    )
    return {
        "application_id": application_id,
        "status": status,
        "result": result,
        "current_url": current_url,
        "screenshot_path": str(screenshot_path),
    }


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            run_easy_apply_review(
                application_id=args.application_id,
                cdp_url=args.cdp_url,
                overrides=_load_overrides(args.overrides_file),
                submit=args.submit,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
