"""Classify form fields — decide what each element needs and propose fill actions."""
from __future__ import annotations

import re

from app.application.easy_apply.parse import has_effective_field_value, normalize_apply_text
from app.application.easy_apply.answers import resolve_candidate_value_for_label
from app.models import (
    LinkedInApplicationFormAction,
    LinkedInApplicationFormElement,
    LinkedInApplicationFormStep,
    LinkedInApplicationQuestion,
    LinkedInCandidateDossier,
)


# ---------------------------------------------------------------------------
# Element inspection helpers
# ---------------------------------------------------------------------------

def _element_has_validation_error(element: LinkedInApplicationFormElement) -> bool:
    return bool(normalize_apply_text(element.constraints.validation_message))


def _has_valid_effective_value(element: LinkedInApplicationFormElement) -> bool:
    return has_effective_field_value(element.current_value) and not _element_has_validation_error(element)


# ---------------------------------------------------------------------------
# Question building — which elements need answers?
# ---------------------------------------------------------------------------

def question_input_type(element: LinkedInApplicationFormElement) -> str:
    if element.control_type == "radio_group" and {normalize_apply_text(option) for option in element.options} == {"yes", "no"}:
        return "yes_no"
    if element.control_type in {"radio_group", "select", "document_choice"}:
        return "select_one"
    if element.control_type == "numeric_text":
        return "numeric"
    if element.control_type == "textarea":
        return "long_text"
    return "short_text"


def is_generation_field(element: LinkedInApplicationFormElement) -> bool:
    label = normalize_apply_text(element.label)
    return any(token in label for token in ("cover letter", "headline", "summary"))


def question_key_from_element(element: LinkedInApplicationFormElement) -> str:
    base = element.element_id or element.label
    return re.sub(r"[^a-z0-9]+", "_", normalize_apply_text(base)).strip("_") or "question"


def collect_preview_questions_from_step(step: LinkedInApplicationFormStep) -> list[LinkedInApplicationQuestion]:
    questions: list[LinkedInApplicationQuestion] = []
    for element in step.elements:
        if _has_valid_effective_value(element) and not is_generation_field(element):
            continue
        if not element.required and not is_generation_field(element):
            continue
        questions.append(
            LinkedInApplicationQuestion(
                question_key=question_key_from_element(element),
                prompt_text=element.label,
                input_type=question_input_type(element),
                required=element.required,
                options=element.options,
                current_value=element.current_value,
                step_name=step.step_title,
                field_name=element.field_name,
                field_id=element.field_id,
            )
        )
    return questions


# ---------------------------------------------------------------------------
# Preview fill actions — what action to take for each element?
# ---------------------------------------------------------------------------

def first_non_placeholder_option(options: list[str]) -> str | None:
    for option in options:
        normalized = normalize_apply_text(option)
        if not normalized:
            continue
        if "select" in normalized or "sélectionnez" in normalized:
            continue
        return option
    return options[0] if options else None


def _pick_radio_option(element: LinkedInApplicationFormElement) -> str | None:
    options = element.options
    if not options:
        return None
    normalized_options = {normalize_apply_text(option): option for option in options}
    for candidate in (
        "yes (work permit)",
        "yes (permanent resident)",
        "yes (canadian citizen)",
        "yes",
        "no",
    ):
        if candidate in normalized_options:
            return normalized_options[candidate]
    return options[-1]


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return None


def _constraint_aware_numeric_preview_value(element: LinkedInApplicationFormElement) -> str:
    constraints = element.constraints
    min_value = _parse_int(constraints.min_value)
    max_value = _parse_int(constraints.max_value)
    validation_message = normalize_apply_text(constraints.validation_message)
    between_match = re.search(r"between\s+(-?\d+)\s+and\s+(-?\d+)", validation_message)
    if between_match:
        min_value = int(between_match.group(1))
        max_value = int(between_match.group(2))

    if min_value is not None or max_value is not None:
        candidate = min_value if min_value is not None else 1
        if max_value is not None:
            candidate = min(candidate, max_value)
        return str(candidate)
    return "1"


def _generic_text_preview_value(element: LinkedInApplicationFormElement) -> str | None:
    if element.control_type == "email":
        return "preview@example.com"
    if element.control_type == "tel":
        return "1111111111"
    if element.control_type == "url":
        return "https://example.com"
    if element.control_type == "textarea":
        return "Development preview placeholder."
    return "Preview Placeholder"


def propose_preview_fill_action(
    dossier: LinkedInCandidateDossier,
    element: LinkedInApplicationFormElement,
) -> LinkedInApplicationFormAction | None:
    if _has_valid_effective_value(element):
        return LinkedInApplicationFormAction(
            element_id=element.element_id,
            action_type="leave_as_is",
            reason="Required field already has a value.",
        )

    candidate_value = resolve_candidate_value_for_label(dossier, element.label)
    if not element.required:
        return None

    if element.control_type == "document_choice":
        choice = first_non_placeholder_option(element.options)
        if choice:
            return LinkedInApplicationFormAction(
                element_id=element.element_id,
                action_type="choose_existing",
                target_value=choice,
                reason="Choosing the first available existing document for preview flow.",
            )
        return None

    if element.control_type == "typeahead":
        target = candidate_value or dossier.contact.city
        return LinkedInApplicationFormAction(
            element_id=element.element_id,
            action_type="select_suggestion",
            target_value=target,
            reason="Using preview typeahead value.",
        )

    if element.control_type == "select":
        if candidate_value:
            return LinkedInApplicationFormAction(
                element_id=element.element_id,
                action_type="choose_option",
                target_value=candidate_value,
                reason="Using dossier-backed select choice.",
            )
        choice = first_non_placeholder_option(element.options)
        if choice:
            return LinkedInApplicationFormAction(
                element_id=element.element_id,
                action_type="choose_option",
                target_value=choice,
                reason="Using the first non-placeholder option for preview.",
            )
        return None

    if element.control_type == "radio_group":
        if candidate_value:
            return LinkedInApplicationFormAction(
                element_id=element.element_id,
                action_type="choose_option",
                target_value=candidate_value,
                reason="Using dossier-backed radio choice.",
            )
        choice = _pick_radio_option(element)
        if choice:
            return LinkedInApplicationFormAction(
                element_id=element.element_id,
                action_type="choose_option",
                target_value=choice,
                reason="Using a generic valid radio option for preview.",
            )
        return None

    if element.control_type == "numeric_text":
        if candidate_value:
            return LinkedInApplicationFormAction(
                element_id=element.element_id,
                action_type="set_text",
                target_value=candidate_value,
                reason="Using dossier-backed numeric value.",
            )
        return LinkedInApplicationFormAction(
            element_id=element.element_id,
            action_type="set_text",
            target_value=_constraint_aware_numeric_preview_value(element),
            reason="Using a constraint-aware numeric preview value.",
        )

    if element.control_type in {"text", "email", "tel", "url", "textarea"}:
        value = candidate_value or _generic_text_preview_value(element)
        if value:
            return LinkedInApplicationFormAction(
                element_id=element.element_id,
                action_type="set_text",
                target_value=value,
                reason="Using preview text value.",
            )

    return LinkedInApplicationFormAction(
        element_id=element.element_id,
        action_type="ask_user",
        reason="Required control could not be filled from preview logic.",
    )


# ---------------------------------------------------------------------------
# Route builder — combines classification + action into a route record
# ---------------------------------------------------------------------------

def build_preview_route(
    dossier: LinkedInCandidateDossier,
    element: LinkedInApplicationFormElement,
    *,
    llm_question_keys: set[str],
) -> tuple[dict[str, object], LinkedInApplicationFormAction | None]:
    action = propose_preview_fill_action(dossier, element)
    question_key = question_key_from_element(element)

    if _has_valid_effective_value(element) and not is_generation_field(element):
        preview_resolution = "already_filled"
    elif _element_has_validation_error(element):
        preview_resolution = "preview_retry_after_validation"
    elif not element.required and not is_generation_field(element):
        preview_resolution = "optional_skip"
    elif action is None:
        preview_resolution = "no_preview_action"
    elif action.action_type == "ask_user":
        preview_resolution = "preview_needs_user_input"
    elif action.action_type == "leave_as_is":
        preview_resolution = "already_filled"
    else:
        preview_resolution = "preview_fill"

    route = {
        "element_id": element.element_id,
        "question_key": question_key,
        "label": element.label,
        "control_type": element.control_type,
        "required": element.required,
        "current_value": element.current_value,
        "preview_resolution": preview_resolution,
        "sent_to_llm": question_key in llm_question_keys,
    }
    if action is not None:
        route["preview_action"] = action.model_dump(mode="json")
    return route, action
