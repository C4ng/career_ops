"""Walk the multi-step Easy Apply form to the review boundary."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from app.application.easy_apply.parse import normalize_apply_text

# Named timeout constants (all in milliseconds)
_NAVIGATE_TIMEOUT_MS = 30_000      # page.goto domcontentloaded
_NETWORKIDLE_TIMEOUT_MS = 10_000   # wait_for_load_state networkidle
_POST_NAVIGATE_WAIT_MS = 1_800     # settle after navigation
_ADVANCE_CLICK_TIMEOUT_MS = 10_000 # button.click when advancing a step
_POST_ADVANCE_WAIT_MS = 1_800      # settle after step advance
from app.utils.retry import retry_with_backoff
from app.application.easy_apply.fill import apply_probe_action
from app.application.easy_apply.parse import extract_easy_apply_form_step
from app.application.easy_apply.classify import collect_preview_questions_from_step
from app.application.easy_apply.classify import build_preview_route
from app.models import (
    LinkedInApplicationFormAction,
    LinkedInApplicationFormElement,
    LinkedInApplicationFormStep,
    LinkedInApplicationQuestion,
    LinkedInCandidateDossier,
)
from app.services.llm.config import ApplicationQuestionMappingLLMConfig

logger = logging.getLogger(__name__)


def _screenshot_path(base_dir: Path, *, step_index: int) -> Path:
    """Return the path for a step screenshot. Does NOT create directories."""
    return base_dir / f"step{step_index}.png"


def _append_collected_questions(
    result: dict[str, object],
    *,
    preview_questions: list[LinkedInApplicationQuestion],
    seen_question_keys: set[str],
) -> None:
    for question in preview_questions:
        if question.question_key in seen_question_keys:
            continue
        seen_question_keys.add(question.question_key)
        result["collected_questions"].append(question.model_dump(mode="json"))


def _execution_record(
    *,
    element: LinkedInApplicationFormElement,
    question_key: str,
    execution_type: str,
    applied: bool,
    action: LinkedInApplicationFormAction,
) -> dict[str, object]:
    return {
        "element_id": element.element_id,
        "question_key": question_key,
        "label": element.label,
        "control_type": element.control_type,
        "execution_type": execution_type,
        "applied": applied,
        "action": action.model_dump(mode="json"),
    }


def _element_trace_summary(element: LinkedInApplicationFormElement) -> dict[str, object]:
    return {
        "element_id": element.element_id,
        "label": element.label,
        "control_type": element.control_type,
        "required": element.required,
        "current_value": element.current_value,
        "options": element.options,
        "field_name": element.field_name,
        "field_id": element.field_id,
    }


def _step_trace_summary(step: LinkedInApplicationFormStep) -> dict[str, object]:
    return {
        "step_title": step.step_title,
        "progress_percent": step.progress_percent,
        "section_titles": step.section_titles,
        "primary_action_label": step.primary_action_label,
        "secondary_action_labels": step.secondary_action_labels,
        "elements": [_element_trace_summary(element) for element in step.elements],
        "record_lists": [record_list.model_dump(mode="json") for record_list in step.record_lists],
    }


def _handle_step_execution(
    page: Page,
    *,
    modal: Any,
    step_index: int,
    dossier: LinkedInCandidateDossier,
    step: LinkedInApplicationFormStep,
    llm_question_keys: set[str],
    result: dict[str, object],
    llm_config: ApplicationQuestionMappingLLMConfig | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    step_routes: list[dict[str, object]] = []
    step_execution: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []

    for element in step.elements:
        route, action = build_preview_route(
            dossier,
            element,
            llm_question_keys=llm_question_keys,
        )
        step_routes.append(route)
        if action is None:
            continue
        if action.action_type == "leave_as_is":
            step_execution.append(
                _execution_record(
                    element=element,
                    question_key=route["question_key"],
                    execution_type="leave_as_is",
                    applied=True,
                    action=action,
                )
            )
            continue
        if action.action_type == "ask_user":
            unresolved.append({"element": element.model_dump(mode="json"), "action": action.model_dump(mode="json")})
            step_execution.append(
                _execution_record(
                    element=element,
                    question_key=route["question_key"],
                    execution_type="needs_user_input",
                    applied=False,
                    action=action,
                )
            )
            continue

        applied = apply_probe_action(page, modal=modal, element=element, action=action, llm_config=llm_config)
        result["actions_taken"].append(
            {
                "step": step_index,
                "element_id": element.element_id,
                "label": element.label,
                "control_type": element.control_type,
                "applied": applied,
                **action.model_dump(mode="json"),
            }
        )
        step_execution.append(
            _execution_record(
                element=element,
                question_key=route["question_key"],
                execution_type="preview_fill",
                applied=applied,
                action=action,
            )
        )

    return step_routes, step_execution, unresolved


def _finalize_stop(
    result: dict[str, object],
    *,
    step_record: dict[str, object],
    status: str,
    primary_result: str,
    unresolved: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    step_record["primary_action"] = {
        "label": step_record["capture"].get("primary_action_label"),
        "clicked": False,
        "result": primary_result,
    }
    result["steps"].append(step_record)
    result["status"] = status
    if unresolved:
        result["unresolved"] = unresolved
    return result


def _advance_step(page: Page, *, modal: Any, step: LinkedInApplicationFormStep) -> dict[str, object]:
    buttons = modal.locator("button")
    if buttons.count() == 0:
        raise RuntimeError("No buttons found in modal — cannot advance step")
    button = buttons.last
    button.click(timeout=_ADVANCE_CLICK_TIMEOUT_MS)
    page.wait_for_timeout(_POST_ADVANCE_WAIT_MS)
    next_step = extract_easy_apply_form_step(page)
    return {
        "label": step.primary_action_label,
        "clicked": True,
        "result": "advanced"
        if (
            next_step.progress_percent != step.progress_percent
            or next_step.section_titles != step.section_titles
            or [element.label for element in next_step.elements] != [element.label for element in step.elements]
        )
        else "same_step_after_click",
        "next_step_preview": {
            "step_title": next_step.step_title,
            "progress_percent": next_step.progress_percent,
            "primary_action_label": next_step.primary_action_label,
            "section_titles": next_step.section_titles,
        },
    }


def _navigate_to_apply_link(page: Page, apply_link: str, *, max_attempts: int = 3) -> None:
    """Navigate to *apply_link* with retry on Playwright TimeoutError."""
    def _goto() -> None:
        page.goto(apply_link, wait_until="domcontentloaded", timeout=_NAVIGATE_TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=_NETWORKIDLE_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            pass

    retry_with_backoff(
        _goto,
        max_attempts=max_attempts,
        retryable=lambda exc: isinstance(exc, PlaywrightTimeoutError),
        operation_name="browser_navigate",
        backoff_base_seconds=2.0,
    )


def run_easy_apply_to_review(
    page: Page,
    *,
    apply_link: str,
    dossier: LinkedInCandidateDossier,
    screenshot_dir: Path,
    llm_config: ApplicationQuestionMappingLLMConfig | None = None,
    max_steps: int = 12,
) -> dict[str, object]:
    logger.info(
        "Easy Apply workflow started",
        extra={
            "apply_link": apply_link,
            "screenshot_dir": str(screenshot_dir),
            "max_steps": max_steps,
        },
    )
    _navigate_to_apply_link(page, apply_link)
    page.wait_for_timeout(_POST_NAVIGATE_WAIT_MS)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    dialogs = page.locator("div[role='dialog']")
    if dialogs.count() == 0:
        raise RuntimeError("Easy Apply dialog not found after navigation")
    modal = dialogs.last
    result: dict[str, object] = {
        "actions_taken": [],
        "steps": [],
        "collected_questions": [],
        "final_url": None,
        "final_modal_text_preview": None,
    }
    seen_question_keys: set[str] = set()
    consecutive_same_step_after_clicks = 0

    for step_index in range(1, max_steps + 1):
        step = extract_easy_apply_form_step(page)
        screenshot_path = _screenshot_path(screenshot_dir, step_index=step_index)
        try:
            page.screenshot(path=str(screenshot_path), full_page=False)
        except Exception as screenshot_exc:
            logger.warning("Failed to capture screenshot", extra={"path": str(screenshot_path), "error": str(screenshot_exc)})
        preview_questions = collect_preview_questions_from_step(step)
        llm_question_keys = {question.question_key for question in preview_questions}
        logger.info(
            "Easy Apply step extracted",
            extra={
                "step_index": step_index,
                "screenshot": str(screenshot_path),
                "step_capture": _step_trace_summary(step),
                "preview_questions": [question.model_dump(mode="json") for question in preview_questions],
            },
        )

        _append_collected_questions(
            result,
            preview_questions=preview_questions,
            seen_question_keys=seen_question_keys,
        )
        step_routes, step_execution, unresolved = _handle_step_execution(
            page,
            modal=modal,
            step_index=step_index,
            dossier=dossier,
            step=step,
            llm_question_keys=llm_question_keys,
            result=result,
            llm_config=llm_config,
        )

        result["final_url"] = page.url
        result["final_modal_text_preview"] = modal.inner_text()[:5000]
        step_record = {
            "step_index": step_index,
            "capture": step.model_dump(mode="json"),
            "preview_questions": [question.model_dump(mode="json") for question in preview_questions],
            "routing": step_routes,
            "execution": step_execution,
            "screenshot": str(screenshot_path),
        }
        logger.info(
            "Easy Apply step routing and execution",
            extra={
                "step_index": step_index,
                "routing": step_routes,
                "execution": step_execution,
                "unresolved": unresolved,
            },
        )
        if unresolved:
            logger.info(
                "Easy Apply workflow paused for user input",
                extra={
                    "step_index": step_index,
                    "status": "needs_user_input",
                    "unresolved": unresolved,
                },
            )
            return _finalize_stop(
                result,
                step_record=step_record,
                status="needs_user_input",
                primary_result="stopped_for_user_input",
                unresolved=unresolved,
            )

        primary_text = normalize_apply_text(step.primary_action_label)
        if primary_text in {"submit application", "submit"}:
            logger.info(
                "Easy Apply workflow reached review boundary",
                extra={
                    "step_index": step_index,
                    "status": "submit_visible",
                    "primary_action_label": step.primary_action_label,
                },
            )
            return _finalize_stop(
                result,
                step_record=step_record,
                status="submit_visible",
                primary_result="submit_visible_stop",
            )

        step_record["primary_action"] = _advance_step(page, modal=modal, step=step)
        logger.info(
            "Easy Apply primary action advanced",
            extra={
                "step_index": step_index,
                "primary_action": step_record["primary_action"],
            },
        )
        if step_record["primary_action"].get("result") == "same_step_after_click":
            consecutive_same_step_after_clicks += 1
            result["steps"].append(step_record)
            if consecutive_same_step_after_clicks >= 2:
                logger.info(
                    "Easy Apply workflow stalled on same step after repeated primary actions",
                    extra={
                        "step_index": step_index,
                        "status": "same_step_after_click",
                        "primary_action": step_record["primary_action"],
                    },
                )
                result["status"] = "same_step_after_click"
                return result
            continue
        consecutive_same_step_after_clicks = 0
        result["steps"].append(step_record)

    result["status"] = "max_steps_reached"
    logger.info(
        "Easy Apply workflow stopped at max steps",
        extra={
            "status": result["status"],
            "step_count": len(result["steps"]),
            "final_url": result["final_url"],
        },
    )
    return result
