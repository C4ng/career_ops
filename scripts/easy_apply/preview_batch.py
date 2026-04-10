from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
from pathlib import Path

import yaml

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from playwright.sync_api import sync_playwright

from app.application.easy_apply.parse import extract_easy_apply_form_step
from app.prompts.application.question_mapping import APPLICATION_QUESTION_MAPPING_SYSTEM_PROMPT
from app.application.easy_apply.review import apply_review_overrides_in_open_modal
from app.application.easy_apply.answers import (
    map_questions_with_llm_debug as map_easy_apply_questions_with_llm_debug,
    resolve_questions_from_dossier as resolve_easy_apply_questions_from_dossier,
)
from app.application.easy_apply.navigate import run_easy_apply_to_review
from app.models import DEFAULT_CDP_URL, LinkedInApplicationQuestion, LinkedInCandidateDossier
from app.logging_setup import setup_logging
from app.settings import (
    load_application_question_mapping_llm_config,
    load_sqlite_config,
)
from app.services.storage import (
    connect_sqlite,
    get_or_create_job_application,
    initialize_schema,
    replace_application_questions,
    update_job_application_status,
)
from app.services.storage.db import resolve_db_path


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Development-only preview pass plus one-shot LLM question batch for Easy Apply."
    )
    parser.add_argument("--apply-link", required=True, help="Saved LinkedIn Easy Apply link to probe.")
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help="Chrome DevTools Protocol URL for the logged-in browser session.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Maximum modal steps to walk during the preview pass.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "data" / "reviews" / "easy_apply_preview_batch.latest.json"),
        help="Where to write the development artifact JSON.",
    )
    parser.add_argument(
        "--screenshots-dir",
        default=str(REPO_ROOT / "data" / "reviews" / "easy_apply_preview_batch.latest"),
        help="Directory for step screenshots.",
    )
    parser.add_argument(
        "--trace-output",
        default=str(REPO_ROOT / "data" / "reviews" / "easy_apply_preview_batch.latest.trace.zip"),
        help="Where to write the Playwright trace zip for this run.",
    )
    parser.add_argument(
        "--dossier-file",
        default=str(REPO_ROOT / "secrets" / "application_candidate_dossier.dev.yaml"),
        help="Optional development-only candidate dossier YAML override.",
    )
    return parser.parse_args()


def _load_dossier_override(path: Path) -> LinkedInCandidateDossier:
    if not path.exists():
        return LinkedInCandidateDossier()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return LinkedInCandidateDossier.model_validate(payload)


def _extract_linkedin_job_id(apply_link: str) -> str | None:
    match = re.search(r"/jobs/view/(\d+)", apply_link)
    return match.group(1) if match else None


def _load_job_context(linkedin_job_id: str | None) -> dict[str, object] | None:
    if not linkedin_job_id:
        return None
    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(REPO_ROOT, sqlite_config)
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT title, company, location_text, work_mode, employment_type, salary_text,
                   company_intro, role_scope, requirements
            FROM jobs
            WHERE linkedin_job_id = ?
            """,
            (linkedin_job_id,),
        ).fetchone()
    if row is None:
        return None
    title, company, location_text, work_mode, employment_type, salary_text, company_intro, role_scope, requirements = row
    context: dict[str, object] = {
        "linkedin_job_id": linkedin_job_id,
        "title": title,
        "company": company,
        "location_text": location_text,
        "work_mode": work_mode,
        "employment_type": employment_type,
        "salary_text": salary_text,
    }
    for key, value in (
        ("company_intro", company_intro),
        ("role_scope", role_scope),
        ("requirements", requirements),
    ):
        if not value:
            continue
        try:
            context[key] = json.loads(value)
        except Exception:
            context[key] = value
    return context


def _load_job_application_seed(linkedin_job_id: str | None) -> dict[str, object] | None:
    if not linkedin_job_id:
        return None
    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(REPO_ROOT, sqlite_config)
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                j.id,
                j.linkedin_job_id,
                COALESCE(r.prompt_version, ''),
                COALESCE(r.profile_version, ''),
                COALESCE(r.recommendation, '')
            FROM jobs j
            LEFT JOIN job_rankings r
              ON r.linkedin_job_id = j.linkedin_job_id
            WHERE j.linkedin_job_id = ?
            ORDER BY r.id DESC
            LIMIT 1
            """,
            (linkedin_job_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "job_id": int(row[0]),
        "linkedin_job_id": row[1],
        "ranking_prompt_version": row[2],
        "ranking_profile_version": row[3],
        "recommendation": row[4],
    }


def _find_element_for_question(preview_result: dict[str, object], question_key: str) -> dict[str, object] | None:
    for step in preview_result.get("steps", []):
        preview_questions = step.get("preview_questions", [])
        matched_question = next((item for item in preview_questions if item.get("question_key") == question_key), None)
        if matched_question is None:
            continue
        capture = step.get("capture", {})
        elements = capture.get("elements", [])
        for element in elements:
            if matched_question.get("field_id") and element.get("field_id") == matched_question.get("field_id"):
                return {"step_index": step.get("step_index"), "step_title": capture.get("step_title"), "element": element}
            if matched_question.get("field_name") and element.get("field_name") == matched_question.get("field_name"):
                return {"step_index": step.get("step_index"), "step_title": capture.get("step_title"), "element": element}
            if element.get("label") == matched_question.get("prompt_text"):
                return {"step_index": step.get("step_index"), "step_title": capture.get("step_title"), "element": element}
    return None


def _executor_action_for_control_type(control_type: str | None) -> str:
    if control_type == "typeahead":
        return "select_suggestion"
    if control_type == "document_choice":
        return "choose_existing"
    if control_type in {"select", "radio_group", "checkbox"}:
        return "choose_option"
    return "set_text"


def _build_question_rows_for_review(preview_result: dict[str, object]) -> list[dict[str, object]]:
    question_rows: list[dict[str, object]] = []
    for step in preview_result.get("steps", []):
        for question in step.get("preview_questions", []):
            question_rows.append(
                {
                    "step_index": step.get("step_index"),
                    **question,
                }
            )
    return question_rows


def _build_execution_logic(
    preview_result: dict[str, object],
    proposals,
) -> list[dict[str, object]]:
    execution_logic: list[dict[str, object]] = []
    for proposal in proposals:
        matched = _find_element_for_question(preview_result, proposal.question_key)
        element = matched.get("element") if matched else None
        control_type = element.get("control_type") if element else None
        execution_logic.append(
            {
                "question_key": proposal.question_key,
                "step_index": matched.get("step_index") if matched else None,
                "step_title": matched.get("step_title") if matched else None,
                "label": element.get("label") if element else None,
                "control_type": control_type,
                "executor_action": (
                    "pause_for_review"
                    if proposal.requires_user_input or not proposal.answer_value
                    else _executor_action_for_control_type(control_type)
                ),
                "answer_value": proposal.answer_value,
                "requires_user_input": proposal.requires_user_input,
                "confidence": proposal.confidence,
                "reason": proposal.reason,
            }
        )
    return execution_logic


def _persist_application_session(
    *,
    job_seed: dict[str, object] | None,
    preview_result: dict[str, object],
    proposals,
) -> dict[str, object] | None:
    if not job_seed:
        return None

    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(REPO_ROOT, sqlite_config)
    connection = connect_sqlite(db_path)
    try:
        initialize_schema(connection)
        application_id, application_created = get_or_create_job_application(
            connection,
            job_id=job_seed["job_id"],
            linkedin_job_id=job_seed["linkedin_job_id"],
            application_type="linkedin_easy_apply",
            ranking_prompt_version=job_seed["ranking_prompt_version"],
            ranking_profile_version=job_seed["ranking_profile_version"],
            recommendation=job_seed["recommendation"],
        )
        proposals_by_key = {proposal.question_key: proposal for proposal in proposals}
        question_count_saved = 0
        for step in preview_result.get("steps", []):
            step_questions = [
                LinkedInApplicationQuestion.model_validate(item)
                for item in step.get("preview_questions", [])
            ]
            if not step_questions:
                continue
            question_count_saved += replace_application_questions(
                connection,
                application_id=application_id,
                job_id=job_seed["job_id"],
                linkedin_job_id=job_seed["linkedin_job_id"],
                step_index=int(step["step_index"]),
                step_name=step.get("capture", {}).get("step_title"),
                questions=step_questions,
                proposals_by_key=proposals_by_key,
            )

        final_status = "review_ready" if preview_result.get("status") == "submit_visible" else "needs_user_input"
        update_job_application_status(
            connection,
            application_id,
            status=final_status,
            pause_reason=None if final_status == "review_ready" else "Pending human review or unresolved answers.",
            review_step_name=preview_result.get("steps", [{}])[-1].get("capture", {}).get("step_title")
            if preview_result.get("steps")
            else None,
            last_seen_url=preview_result.get("final_url"),
            last_screenshot_path=preview_result.get("steps", [{}])[-1].get("screenshot")
            if preview_result.get("steps")
            else None,
        )
        return {
            "application_id": application_id,
            "application_created": application_created,
            "question_count_saved": question_count_saved,
            "status": final_status,
        }
    finally:
        connection.close()


def _build_preview_batch_result(
    *,
    args: argparse.Namespace,
    llm_config,
    job_context: dict[str, object] | None,
    application_summary: dict[str, object] | None,
    preview_result: dict[str, object],
    review_apply_result: dict[str, object] | None,
    deterministic_proposals,
    questions: list[LinkedInApplicationQuestion],
    llm_input: dict[str, object],
    raw_response_payload: dict[str, object],
    raw_output_text: str,
    proposals,
    execution_logic: list[dict[str, object]],
    trace_path: str | None,
) -> dict[str, object]:
    deterministic_keys = {proposal.question_key for proposal in deterministic_proposals}
    preview_steps = preview_result.get("steps", [])
    data_flow = {
        "step_count": len(preview_steps),
        "question_count": len(questions),
        "resolved_without_llm_count": len(deterministic_proposals),
        "llm_question_count": len([question for question in questions if question.question_key not in deterministic_keys]),
        "proposal_count": len(proposals),
        "status": preview_result.get("status"),
        "steps": [
            {
                "step_index": step.get("step_index"),
                "step_title": step.get("capture", {}).get("step_title"),
                "progress_percent": step.get("capture", {}).get("progress_percent"),
                "fields": [
                    {
                        "label": route.get("label"),
                        "control_type": route.get("control_type"),
                        "required": route.get("required"),
                        "current_value": route.get("current_value"),
                        "preview_resolution": route.get("preview_resolution"),
                        "preview_action": route.get("preview_action"),
                        "sent_to_llm": route.get("sent_to_llm"),
                    }
                    for route in step.get("routing", [])
                ],
                "execution": step.get("execution", []),
                "primary_action": step.get("primary_action"),
            }
            for step in preview_steps
        ],
    }
    return {
        "apply_link": args.apply_link,
        "job_context": job_context,
        "application": application_summary,
        "llm_model": llm_config.model,
        "prompt_version": llm_config.prompt_version,
        "trace_path": trace_path,
        "preview": preview_result,
        "data_flow": data_flow,
        "review_apply_result": review_apply_result,
        "resolved_without_llm": {
            "question_count": len(deterministic_proposals),
            "questions": [
                question.model_dump(mode="json")
                for question in questions
                if question.question_key in deterministic_keys
            ],
            "proposals": [proposal.model_dump(mode="json") for proposal in deterministic_proposals],
        },
        "llm_input": {
            "system_prompt": APPLICATION_QUESTION_MAPPING_SYSTEM_PROMPT,
            "user_payload": llm_input,
        },
        "llm_output": {
            "raw_response_payload": raw_response_payload,
            "raw_output_text": raw_output_text,
            "parsed_proposals": [proposal.model_dump(mode="json") for proposal in proposals],
        },
        "execution_logic": execution_logic,
    }


def main() -> int:
    args = parse_args()
    setup_logging("linkedin_easy_apply_preview_batch")
    llm_config = load_application_question_mapping_llm_config()
    dossier = _load_dossier_override(Path(args.dossier_file))
    linkedin_job_id = _extract_linkedin_job_id(args.apply_link)
    job_context = _load_job_context(linkedin_job_id)
    job_seed = _load_job_application_seed(linkedin_job_id)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    screenshots_dir = Path(args.screenshots_dir)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    trace_output = Path(args.trace_output)
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    review_apply_result: dict[str, object] | None = None
    preview_result: dict[str, object]
    llm_input: dict[str, object]
    raw_response_payload: dict[str, object]
    raw_output_text: str
    proposals = []
    deterministic_proposals = []
    unresolved_questions = []
    question_rows_for_review: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        context = browser.contexts[0]
        trace_started = False
        try:
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
            trace_started = True
            logger.info("Easy Apply Playwright tracing started", extra={"trace_output": str(trace_output)})
        except Exception:
            logger.exception("Easy Apply Playwright tracing failed to start", extra={"trace_output": str(trace_output)})
        page = context.new_page()
        try:
            preview_result = run_easy_apply_to_review(
                page,
                apply_link=args.apply_link,
                dossier=dossier,
                screenshot_dir=screenshots_dir,
                max_steps=args.max_steps,
            )
            questions = [
                LinkedInApplicationQuestion.model_validate(item)
                for item in preview_result.get("collected_questions", [])
            ]
            deterministic_proposals, unresolved_questions = resolve_easy_apply_questions_from_dossier(dossier, questions)
            llm_input, raw_response_payload, raw_output_text, proposals = map_easy_apply_questions_with_llm_debug(
                llm_config,
                dossier,
                questions,
                job_context=job_context,
            )
            question_rows_for_review = _build_question_rows_for_review(preview_result)
            overrides = {
                proposal.question_key: proposal.answer_value
                for proposal in proposals
                if proposal.answer_value and not proposal.requires_user_input
            }
            review_apply_result = apply_review_overrides_in_open_modal(
                page,
                question_rows=question_rows_for_review,
                overrides=overrides,
                submit=False,
            )
            if review_apply_result.get("status") == "review_ready":
                final_step = extract_easy_apply_form_step(page)
                preview_result["final_url"] = page.url
                preview_result["final_modal_text_preview"] = page.locator("div[role='dialog']").last.inner_text()[:5000]
                preview_result["final_step_after_review_apply"] = final_step.model_dump(mode="json")
        finally:
            if trace_started:
                try:
                    context.tracing.stop(path=str(trace_output))
                    logger.info("Easy Apply Playwright tracing saved", extra={"trace_output": str(trace_output)})
                except Exception:
                    logger.exception("Easy Apply Playwright tracing failed to save", extra={"trace_output": str(trace_output)})
    execution_logic = _build_execution_logic(preview_result, proposals)

    application_summary = _persist_application_session(
        job_seed=job_seed,
        preview_result=preview_result,
        proposals=proposals,
    )

    result = _build_preview_batch_result(
        args=args,
        llm_config=llm_config,
        job_context=job_context,
        application_summary=application_summary,
        preview_result=preview_result,
        review_apply_result=review_apply_result,
        deterministic_proposals=deterministic_proposals,
        questions=questions,
        llm_input=llm_input,
        raw_response_payload=raw_response_payload,
        raw_output_text=raw_output_text,
        proposals=proposals,
        execution_logic=execution_logic,
        trace_path=str(trace_output) if trace_output.exists() else None,
    )

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    logger.debug(
        "Easy Apply preview batch artifact",
        extra={
            "preview": preview_result,
            "trace_path": str(trace_output) if trace_output.exists() else None,
            "data_flow": result["data_flow"],
            "llm_input": {
                "system_prompt": APPLICATION_QUESTION_MAPPING_SYSTEM_PROMPT,
                "user_payload": llm_input,
            },
            "llm_output": {
                "raw_response_payload": raw_response_payload,
                "raw_output_text": raw_output_text,
                "parsed_proposals": [proposal.model_dump(mode="json") for proposal in proposals],
            },
            "execution_logic": execution_logic,
        },
    )
    logger.info(
        "Easy Apply preview batch completed",
        extra={
            "apply_link": args.apply_link,
            "step_count": len(preview_result.get("steps", [])),
            "question_count": len(questions),
            "resolved_without_llm": len(deterministic_proposals),
            "llm_question_count": len(unresolved_questions),
            "proposal_count": len(proposals),
            "trace_path": str(trace_output) if trace_output.exists() else None,
            "execution_logic": execution_logic,
        },
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
