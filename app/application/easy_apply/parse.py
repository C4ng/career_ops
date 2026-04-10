"""Parse the Easy Apply modal DOM into clean Pydantic models.

Includes text normalization helpers used across the easy_apply package.
"""
from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Page

from app.models import (
    LinkedInApplicationElementConstraints,
    LinkedInApplicationFormElement,
    LinkedInApplicationFormStep,
    LinkedInApplicationRecordList,
)

# ---------------------------------------------------------------------------
# Text normalization helpers
# ---------------------------------------------------------------------------

PLACEHOLDER_VALUES = frozenset({
    "select an option",
    "sélectionnez une option",
    "select",
    "sélectionnez",
    "choose an option",
})


def normalize_apply_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


def normalize_label(text: str | None) -> str:
    """Normalize a form label, collapsing whitespace and deduplicating
    repeated text that LinkedIn sometimes produces (e.g. 'Email addressEmail address')."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    repeated_sentence = re.match(r"^(.+?[?.!])\s+\1$", cleaned)
    if repeated_sentence:
        return repeated_sentence.group(1).strip()
    midpoint = len(cleaned) // 2
    if len(cleaned) % 2 == 0:
        first = cleaned[:midpoint].strip()
        second = cleaned[midpoint:].strip()
        if first and first == second:
            return first
    duplicated = re.match(r"^(.+?)\1$", cleaned)
    if duplicated:
        return duplicated.group(1).strip()
    repeated_with_suffix = re.match(r"^(.+?)\1(?:\s+Required)?$", cleaned)
    if repeated_with_suffix:
        return repeated_with_suffix.group(1).strip()
    return cleaned


def has_effective_field_value(value: str | None) -> bool:
    normalized = normalize_apply_text(value)
    if not normalized:
        return False
    return normalized not in PLACEHOLDER_VALUES


# ---------------------------------------------------------------------------
# DOM extraction and model coercion
# ---------------------------------------------------------------------------

_PARSE_FORM_JS = (Path(__file__).parent / "parse_form.js").read_text()


def _question_key(prompt_text: str, *, fallback: str) -> str:
    base = prompt_text.strip().lower() or fallback
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return base or fallback


def _is_placeholder_option(text: str | None) -> bool:
    normalized = normalize_label(text).lower()
    return normalized in (PLACEHOLDER_VALUES | {""})


def _normalize_text_list(values: list[object], *, skip_placeholders: bool = False) -> list[str]:
    normalized_values: list[str] = []
    for value in values:
        normalized = normalize_label(str(value))
        if not normalized:
            continue
        if skip_placeholders and _is_placeholder_option(normalized):
            continue
        normalized_values.append(normalized)
    return normalized_values


def _coerce_constraints(item: dict[str, object]) -> LinkedInApplicationElementConstraints:
    return LinkedInApplicationElementConstraints(
        html_type=str(item.get("html_type")) if item.get("html_type") not in (None, "") else None,
        input_mode=str(item.get("input_mode")) if item.get("input_mode") not in (None, "") else None,
        pattern=str(item.get("pattern")) if item.get("pattern") not in (None, "") else None,
        placeholder=str(item.get("placeholder")) if item.get("placeholder") not in (None, "") else None,
        validation_message=(
            normalize_label(str(item.get("validation_message")))
            if item.get("validation_message") not in (None, "", "None")
            else None
        ),
        min_value=str(item.get("min_value")) if item.get("min_value") not in (None, "") else None,
        max_value=str(item.get("max_value")) if item.get("max_value") not in (None, "") else None,
    )


def _coerce_control_type(
    item: dict[str, object],
    *,
    label: str,
    constraints: LinkedInApplicationElementConstraints,
) -> str:
    control_type = str(item.get("control_type") or "text")
    if control_type != "text":
        return control_type

    validation = (constraints.validation_message or "").lower()
    input_mode = (constraints.input_mode or "").lower()
    identifier = " ".join(
        [
            str(item.get("element_id") or ""),
            str(item.get("field_name") or ""),
            str(item.get("field_id") or ""),
            label,
        ]
    ).lower()
    if (
        "number" in validation
        or "decimal" in validation
        or input_mode in {"numeric", "decimal"}
        or any(marker in identifier for marker in ("numeric", "decimal", "salary expectation"))
    ):
        return "numeric_text"
    return control_type


def _coerce_form_element(item: dict[str, object], *, index: int, seen: set[str]) -> LinkedInApplicationFormElement | None:
    label = normalize_label(str(item.get("label") or ""))
    if not label:
        return None

    element_id = str(item.get("element_id") or _question_key(label, fallback=f"element_{index}"))
    if element_id in seen:
        element_id = f"{element_id}_{index}"
    seen.add(element_id)

    constraints = _coerce_constraints(item)
    control_type = _coerce_control_type(item, label=label, constraints=constraints)
    current_value = str(item["current_value"]) if item.get("current_value") not in (None, "") else None
    options = _normalize_text_list(list(item.get("options", [])), skip_placeholders=True)
    suggestions = _normalize_text_list(list(item.get("suggestions", [])))

    return LinkedInApplicationFormElement(
        element_id=element_id,
        label=label,
        control_type=control_type,
        required=bool(item.get("required")),
        current_value=current_value,
        options=options,
        options_count=int(item.get("options_count") or len(options)),
        suggestions=suggestions,
        constraints=constraints,
        field_name=str(item["field_name"]) if item.get("field_name") not in (None, "") else None,
        field_id=str(item["field_id"]) if item.get("field_id") not in (None, "") else None,
    )


def _coerce_form_elements(raw_elements: list[dict[str, object]]) -> list[LinkedInApplicationFormElement]:
    elements: list[LinkedInApplicationFormElement] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_elements, start=1):
        element = _coerce_form_element(item, index=index, seen=seen)
        if element is not None:
            elements.append(element)
    return elements


def _coerce_record_lists(raw_record_lists: list[dict[str, object]]) -> list[LinkedInApplicationRecordList]:
    record_lists: list[LinkedInApplicationRecordList] = []
    for item in raw_record_lists:
        section_title = normalize_label(str(item.get("section_title") or ""))
        item_previews = _normalize_text_list(list(item.get("item_previews", [])))
        if not section_title and not item_previews:
            continue
        record_lists.append(
            LinkedInApplicationRecordList(
                section_title=section_title or "Record list",
                item_previews=item_previews,
                item_count=int(item.get("item_count") or len(item_previews)),
            )
        )
    return record_lists


def _extract_raw_form_step(page: Page) -> dict[str, object]:
    modal = page.locator("div[role='dialog']").last
    return modal.evaluate(_PARSE_FORM_JS)


def _build_form_step(raw_step: dict[str, object], *, page_url: str) -> LinkedInApplicationFormStep:
    section_titles = _normalize_text_list(list(raw_step.get("section_titles", [])))
    secondary_action_labels = _normalize_text_list(list(raw_step.get("secondary_action_labels", [])))
    return LinkedInApplicationFormStep(
        step_title=normalize_label(str(raw_step.get("step_title"))) or None,
        progress_percent=int(raw_step["progress_percent"]) if raw_step.get("progress_percent") is not None else None,
        section_titles=section_titles,
        primary_action_label=normalize_label(str(raw_step.get("primary_action_label"))) or None,
        secondary_action_labels=secondary_action_labels,
        elements=_coerce_form_elements(list(raw_step.get("raw_elements", []))),
        record_lists=_coerce_record_lists(list(raw_step.get("raw_record_lists", []))),
        page_url=page_url,
    )


def extract_easy_apply_form_step(page: Page) -> LinkedInApplicationFormStep:
    raw_step = _extract_raw_form_step(page)
    return _build_form_step(raw_step, page_url=page.url)


def easy_apply_form_step_debug_payload(step: LinkedInApplicationFormStep) -> dict[str, object]:
    return step.model_dump(mode="json")
