from __future__ import annotations

import re
from typing import Iterable

from playwright.sync_api import Browser, Locator, Page

from app.application.easy_apply.parse import normalize_apply_text
from app.application.easy_apply.fill import apply_probe_action
from app.application.easy_apply.parse import extract_easy_apply_form_step
from app.models import LinkedInApplicationFormAction, LinkedInApplicationFormElement

# Named timeout constants (all in milliseconds)
_BUTTON_CLICK_TIMEOUT_MS = 6_000   # generic button clicks
_POST_CLICK_WAIT_MS = 1_200        # settle after a click
_PRIMARY_CLICK_TIMEOUT_MS = 6_000  # primary action button click
_POST_PRIMARY_WAIT_MS = 1_500      # settle after primary action
_SUBMIT_POLL_INTERVAL_MS = 500     # polling interval for submit confirmation
_SUBMIT_CONFIRMATION_TIMEOUT_MS = 12_000  # max wait for submit confirmation signal
_INNER_TEXT_TIMEOUT_MS = 1_000     # inner_text() timeout in submit polling
_EDIT_CLICK_TIMEOUT_MS = 6_000     # clicking edit section links
_POST_EDIT_STEP_WAIT_MS = 400      # brief wait after clicking edit
_EDIT_STEP_POLL_WAIT_MS = 250      # polling for step change after edit click
_EDIT_STEP_POLL_MAX = 8            # max polls when waiting for step to change


def find_open_easy_apply_page(
    browser: Browser,
    *,
    linkedin_job_id: str,
    last_seen_url: str | None = None,
) -> Page | None:
    pages: list[Page] = []
    for context in browser.contexts:
        pages.extend(context.pages)

    def _matches(page: Page) -> bool:
        url = page.url or ""
        if last_seen_url and url == last_seen_url:
            return True
        return linkedin_job_id in url

    for page in reversed(pages):
        try:
            if _matches(page) and page.locator("div[role='dialog']").count():
                return page
        except Exception:
            continue
    return None


def _match_element(
    elements: Iterable[LinkedInApplicationFormElement],
    question: dict[str, object],
) -> LinkedInApplicationFormElement | None:
    question_field_id = question.get("field_id")
    question_field_name = question.get("field_name")
    question_prompt = normalize_apply_text(str(question.get("prompt_text") or ""))
    question_key = normalize_apply_text(str(question.get("question_key") or ""))

    for element in elements:
        if question_field_id and element.field_id == question_field_id:
            return element
    for element in elements:
        if question_field_name and element.field_name == question_field_name:
            return element
    for element in elements:
        if normalize_apply_text(element.label) == question_prompt:
            return element
    for element in elements:
        if question_prompt and question_prompt in normalize_apply_text(element.label):
            return element
    for element in elements:
        element_key = normalize_apply_text(element.element_id)
        if question_key and element_key == question_key:
            return element
    return None


def _override_action_for_element(
    element: LinkedInApplicationFormElement,
    answer_value: str,
) -> LinkedInApplicationFormAction:
    if element.control_type == "typeahead":
        action_type = "select_suggestion"
    elif element.control_type == "document_choice":
        action_type = "choose_existing"
    elif element.control_type in {"select", "radio_group", "checkbox"}:
        action_type = "choose_option"
    else:
        action_type = "set_text"
    return LinkedInApplicationFormAction(
        element_id=element.element_id,
        action_type=action_type,
        target_value=answer_value,
        reason="Applying stored review override.",
        confidence="high",
        review_required=False,
    )


def _modal(page: Page) -> Locator:
    locator = page.locator("div[role='dialog']")
    if locator.count() == 0:
        raise RuntimeError("No Easy Apply dialog found on page")
    return locator.last


def _infer_review_section_labels(question: dict[str, object]) -> list[str]:
    prompt = normalize_apply_text(str(question.get("prompt_text") or ""))
    input_type = normalize_apply_text(str(question.get("input_type") or ""))
    labels: list[str] = []

    if any(
        cue in prompt
        for cue in [
            "first name",
            "last name",
            "email",
            "phone",
            "mobile",
            "location",
            "address",
            "postal",
            "city",
            "country",
        ]
    ):
        labels.append("Contact info")

    if any(cue in prompt for cue in ["resume", "cv"]):
        labels.append("Resume")

    if "cover letter" in prompt:
        labels.append("Cover letter")

    if not labels and input_type in {"radio_group", "select_one", "select", "yes_no", "numeric", "numeric_text"}:
        labels.append("Additional Questions")

    if not labels:
        labels.append("Additional Questions")
    return labels


def _open_review_section_by_aria_label(page: Page, section_label: str) -> bool:
    modal = _modal(page)
    button = modal.locator(f"button[aria-label='Edit {section_label}']").last
    if button.count() == 0:
        return False
    button.click(timeout=_BUTTON_CLICK_TIMEOUT_MS)
    page.wait_for_timeout(_POST_CLICK_WAIT_MS)
    return True


def _click_back(page: Page, *, timeout_ms: int = _BUTTON_CLICK_TIMEOUT_MS) -> bool:
    modal = _modal(page)
    button = modal.locator("button:visible, a:visible").filter(
        has_text=re.compile(r"^Back$", re.IGNORECASE)
    ).last
    if button.count() == 0:
        button = modal.get_by_text(re.compile(r"^back$", re.IGNORECASE), exact=False).last
    if button.count() == 0:
        return False
    button.click(timeout=timeout_ms)
    page.wait_for_timeout(_POST_CLICK_WAIT_MS)
    return True


def _click_primary(page: Page, *, timeout_ms: int = _PRIMARY_CLICK_TIMEOUT_MS) -> str | None:
    step = extract_easy_apply_form_step(page)
    label = step.primary_action_label
    if not label:
        return None
    modal = _modal(page)
    button = modal.locator("button:visible, a:visible").filter(
        has_text=re.compile(f"^{re.escape(label)}$", re.IGNORECASE)
    ).last
    if button.count() == 0:
        button = modal.locator("button").last
    button.click(timeout=timeout_ms)
    page.wait_for_timeout(_POST_PRIMARY_WAIT_MS)
    return label


def _wait_for_submit_success_signal(page: Page, *, timeout_ms: int = _SUBMIT_CONFIRMATION_TIMEOUT_MS) -> bool:
    success_patterns = [
        re.compile(r"application submitted", re.IGNORECASE),
        re.compile(r"your application was sent", re.IGNORECASE),
        re.compile(r"you('ve| have) successfully applied", re.IGNORECASE),
        re.compile(r"applied", re.IGNORECASE),
    ]
    waited_ms = 0
    while waited_ms <= timeout_ms:
        dialog_count = page.locator("div[role='dialog']").count()
        if dialog_count == 0:
            return True
        modal = _modal(page)
        text = ""
        try:
            text = modal.inner_text(timeout=_INNER_TEXT_TIMEOUT_MS)[:5000]
        except Exception:
            text = ""
        lowered = normalize_apply_text(text)
        if any(pattern.search(text) for pattern in success_patterns):
            return True
        try:
            step = extract_easy_apply_form_step(page)
            primary = normalize_apply_text(step.primary_action_label)
            if primary not in {"submit application", "submit"} and "review your application" not in lowered:
                return True
        except Exception:
            pass
        page.wait_for_timeout(_SUBMIT_POLL_INTERVAL_MS)
        waited_ms += _SUBMIT_POLL_INTERVAL_MS
    return False


def _open_matching_edit_section(
    page: Page,
    *,
    question_rows: list[dict[str, object]],
    pending_keys: set[str],
) -> bool:
    preferred_labels: list[str] = []
    seen_labels: set[str] = set()
    for row in question_rows:
        if row["question_key"] not in pending_keys:
            continue
        for label in _infer_review_section_labels(row):
            if label in seen_labels:
                continue
            preferred_labels.append(label)
            seen_labels.add(label)

    for section_label in preferred_labels:
        if not _open_review_section_by_aria_label(page, section_label):
            continue
        step = extract_easy_apply_form_step(page)
        for row in question_rows:
            if row["question_key"] not in pending_keys:
                continue
            if _match_element(step.elements, row) is not None:
                return True
        _click_back(page)

    def _edit_links() -> Locator:
        return _modal(page).locator("button:visible, a:visible").filter(
            has_text=re.compile(r"^Edit$", re.IGNORECASE)
        )

    count = _edit_links().count()
    for reverse_index in range(count - 1, -1, -1):
        edit_links = _edit_links()
        if edit_links.count() <= reverse_index:
            continue
        before_primary = normalize_apply_text(extract_easy_apply_form_step(page).primary_action_label)
        edit_links.nth(reverse_index).click(timeout=_EDIT_CLICK_TIMEOUT_MS)
        page.wait_for_timeout(_POST_EDIT_STEP_WAIT_MS)
        for _ in range(_EDIT_STEP_POLL_MAX):
            step = extract_easy_apply_form_step(page)
            current_primary = normalize_apply_text(step.primary_action_label)
            if current_primary != before_primary:
                break
            page.wait_for_timeout(_EDIT_STEP_POLL_WAIT_MS)
        step = extract_easy_apply_form_step(page)
        for row in question_rows:
            if row["question_key"] not in pending_keys:
                continue
            if _match_element(step.elements, row) is not None:
                return True
        _click_back(page)
    return False


def apply_review_overrides_in_open_modal(
    page: Page,
    *,
    question_rows: list[dict[str, object]],
    overrides: dict[str, str],
    max_back_steps: int = 12,
    max_forward_steps: int = 12,
    submit: bool = False,
) -> dict[str, object]:
    applied_overrides: list[dict[str, object]] = []
    pending = dict(overrides)

    for _ in range(max_back_steps):
        step = extract_easy_apply_form_step(page)
        if pending and normalize_apply_text(step.primary_action_label) in {"submit application", "submit"}:
            if _open_matching_edit_section(
                page,
                question_rows=question_rows,
                pending_keys=set(pending),
            ):
                step = extract_easy_apply_form_step(page)
        if pending:
            for question_key, answer_value in list(pending.items()):
                row = next((item for item in question_rows if item["question_key"] == question_key), None)
                if row is None:
                    continue
                element = _match_element(step.elements, row)
                if element is None:
                    continue
                action = _override_action_for_element(element, answer_value)
                applied = apply_probe_action(page, modal=_modal(page), element=element, action=action)
                applied_overrides.append(
                    {
                        "question_key": question_key,
                        "label": row.get("prompt_text"),
                        "step_title": step.step_title,
                        "applied": applied,
                        "answer_value": answer_value,
                    }
                )
                if applied:
                    pending.pop(question_key, None)
            if not pending:
                break
        if not _click_back(page):
            break

    for _ in range(max_forward_steps):
        step = extract_easy_apply_form_step(page)
        primary = normalize_apply_text(step.primary_action_label)
        if primary in {"submit application", "submit"}:
            if pending:
                return {
                    "status": "submit_blocked_pending_overrides" if submit else "review_ready",
                    "applied_overrides": applied_overrides,
                    "pending_overrides": pending,
                }
            if submit:
                _click_primary(page)
                if _wait_for_submit_success_signal(page):
                    return {
                        "status": "submitted_clicked",
                        "applied_overrides": applied_overrides,
                        "pending_overrides": pending,
                    }
                return {
                    "status": "submit_not_confirmed",
                    "applied_overrides": applied_overrides,
                    "pending_overrides": pending,
                }
            return {
                "status": "review_ready",
                "applied_overrides": applied_overrides,
                "pending_overrides": pending,
            }
        if not step.primary_action_label:
            break
        _click_primary(page)

    return {
        "status": "navigation_incomplete",
        "applied_overrides": applied_overrides,
        "pending_overrides": pending,
    }
