"""Browser interactions to fill Easy Apply form fields — click, type, select."""
from __future__ import annotations

import json
import logging
import re

from playwright.sync_api import Locator, Page

from app.application.easy_apply.parse import normalize_apply_text
from app.prompts.application.question_mapping import OPTION_RESOLVE_RESPONSE_SCHEMA, OPTION_RESOLVE_SYSTEM_PROMPT
from app.models import (
    LinkedInApplicationFormAction,
    LinkedInApplicationFormElement,
)
from app.services.llm.config import ApplicationQuestionMappingLLMConfig
from app.services.llm import request_structured_chat_completion


logger = logging.getLogger(__name__)

# Max candidates passed to the LLM for option resolution.
# Long dropdowns (e.g. country lists) are pre-filtered by prefix/substring before this cap.
_MAX_LLM_OPTIONS = 20

# Timeout constants (milliseconds)
_FIELD_CLICK_TIMEOUT_MS = 5_000
_OPTION_CLICK_TIMEOUT_MS = 5_000
_SUGGESTION_WAIT_MS = 1_200
_POST_SUGGESTION_WAIT_MS = 400


def find_field_locator(modal: Locator, element: LinkedInApplicationFormElement) -> Locator:
    if element.field_id:
        locator = modal.locator(f"#{element.field_id}")
        if locator.count():
            return locator.first
    if element.field_name:
        locator = modal.locator(f'[name="{element.field_name}"]')
        if locator.count():
            return locator.first
    return modal.get_by_label(element.label, exact=False).first


def resolve_option_with_llm(
    llm_config: ApplicationQuestionMappingLLMConfig,
    target_value: str,
    candidates: list[str],
    *,
    field_label: str = "",
) -> str | None:
    """Return the candidate string that best matches *target_value*, using the LLM.

    Tries a normalized exact match first so trivial cases don't burn a network call.
    Returns ``None`` if the LLM judges no candidate to be a reasonable match.
    """
    if not candidates or not target_value:
        return None

    # Exact normalized match — no LLM needed
    norm_target = normalize_apply_text(target_value)
    for candidate in candidates:
        if normalize_apply_text(candidate) == norm_target:
            return candidate

    # Narrow a large list (e.g. 250-entry country dropdown) to at most _MAX_LLM_OPTIONS
    # candidates before the LLM call.  Prefer candidates whose normalized text starts with
    # or contains the target; fall back to the full list only when no prefix hits exist.
    shortlist = candidates
    if len(candidates) > _MAX_LLM_OPTIONS:
        prefix_hits = [c for c in candidates if normalize_apply_text(c).startswith(norm_target)]
        contains_hits = [c for c in candidates if norm_target in normalize_apply_text(c)]
        shortlist = (prefix_hits or contains_hits or candidates)[:_MAX_LLM_OPTIONS]

    user_payload: dict[str, object] = {"target_value": target_value, "options": shortlist}
    if field_label:
        user_payload["field_label"] = field_label

    _, _, raw = request_structured_chat_completion(
        llm_config,
        system_prompt=OPTION_RESOLVE_SYSTEM_PROMPT,
        user_payload=user_payload,
        response_schema=OPTION_RESOLVE_RESPONSE_SCHEMA,
        schema_name="option_resolve",
    )
    result = json.loads(raw)
    best = result.get("best_match")
    resolved = best if isinstance(best, str) and best else None
    logger.debug(
        "Option resolved via LLM",
        extra={"target_value": target_value, "candidates": candidates, "resolved": resolved, "field_label": field_label},
    )
    return resolved


def _apply_text(locator: Locator, value: str) -> None:
    locator.click(timeout=_FIELD_CLICK_TIMEOUT_MS)
    locator.fill(value)


def choose_visible_option(
    modal: Locator,
    target_value: str,
    *,
    llm_config: ApplicationQuestionMappingLLMConfig | None = None,
) -> bool:
    option_label = modal.locator(f'label[data-test-text-selectable-option__label="{target_value}"]').first
    if option_label.count():
        option_label.click(force=True, timeout=_OPTION_CLICK_TIMEOUT_MS)
        return True

    visible_candidates = []
    candidate_nodes = modal.locator("[data-test-text-selectable-option__label], [role='option']")
    for index in range(candidate_nodes.count()):
        text = candidate_nodes.nth(index).inner_text().strip()
        if text:
            visible_candidates.append(text)

    best_match: str | None = None
    if llm_config and visible_candidates:
        best_match = resolve_option_with_llm(llm_config, target_value, visible_candidates)

    if best_match:
        matched_option = modal.get_by_text(best_match, exact=False).first
        if matched_option.count():
            matched_option.click(force=True, timeout=_OPTION_CLICK_TIMEOUT_MS)
            return True

    # Last-resort Playwright substring match
    text_option = modal.get_by_text(target_value, exact=False).first
    if text_option.count():
        text_option.click(force=True, timeout=_OPTION_CLICK_TIMEOUT_MS)
        return True
    return False


def _choose_radio_option_for_element(
    modal: Locator,
    element: LinkedInApplicationFormElement,
    target_value: str,
    *,
    llm_config: ApplicationQuestionMappingLLMConfig | None = None,
) -> bool:
    if element.field_name and target_value in element.options:
        option_index = element.options.index(target_value)
        radio_inputs = modal.locator(f'[name="{element.field_name}"]')
        if radio_inputs.count() > option_index:
            radio_inputs.nth(option_index).check(force=True, timeout=_OPTION_CLICK_TIMEOUT_MS)
            return True

    if element.field_id and target_value in element.options:
        option_index = element.options.index(target_value)
        field_id_prefix = re.sub(r"-\\d+$", "", element.field_id)
        candidate = modal.locator(f'#{field_id_prefix}-{option_index}')
        if candidate.count():
            candidate.first.check(force=True, timeout=_OPTION_CLICK_TIMEOUT_MS)
            return True

    return choose_visible_option(modal, target_value, llm_config=llm_config)


def apply_probe_action(
    page: Page,
    *,
    modal: Locator,
    element: LinkedInApplicationFormElement,
    action: LinkedInApplicationFormAction,
    llm_config: ApplicationQuestionMappingLLMConfig | None = None,
) -> bool:
    if action.action_type in {"leave_as_is", "ask_user"}:
        return True

    if not action.target_value and action.action_type not in {"leave_as_is", "ask_user"}:
        return False

    try:
        if action.action_type == "choose_existing":
            return choose_visible_option(modal, action.target_value or "", llm_config=llm_config)

        if action.action_type == "choose_option":
            if element.control_type == "select":
                locator = find_field_locator(modal, element)
                # Use LLM to resolve action.target_value to the exact option label
                if llm_config and element.options:
                    matched = resolve_option_with_llm(
                        llm_config,
                        action.target_value or "",
                        element.options,
                        field_label=element.label,
                    )
                else:
                    matched = None
                target_option = matched or action.target_value or ""
                try:
                    locator.select_option(label=target_option)
                    return True
                except Exception:
                    try:
                        locator.click(timeout=_FIELD_CLICK_TIMEOUT_MS)
                        page.wait_for_timeout(300)
                    except Exception:
                        pass
                    return choose_visible_option(modal, target_option, llm_config=llm_config)
            if element.control_type == "radio_group":
                return _choose_radio_option_for_element(
                    modal, element, action.target_value or "", llm_config=llm_config
                )
            return choose_visible_option(modal, action.target_value or "", llm_config=llm_config)

        locator = find_field_locator(modal, element)
        if locator.count() == 0:
            return False

        if action.action_type == "set_text":
            _apply_text(locator, action.target_value or "")
            return True

        if action.action_type == "select_suggestion":
            _apply_text(locator, action.target_value or "")
            page.wait_for_timeout(_SUGGESTION_WAIT_MS)
            suggestion_candidates = []
            suggestion_nodes = modal.locator("[role='option'], [data-test-single-typeahead-entity-form-search-result='true']")
            for index in range(suggestion_nodes.count()):
                text = suggestion_nodes.nth(index).inner_text().strip()
                if text:
                    suggestion_candidates.append(text)

            best_suggestion: str | None = None
            if llm_config and suggestion_candidates:
                best_suggestion = resolve_option_with_llm(
                    llm_config, action.target_value or "", suggestion_candidates
                )

            if best_suggestion:
                suggestion = modal.get_by_text(best_suggestion, exact=False).first
            else:
                suggestion = modal.get_by_role("option", name=re.compile(re.escape(action.target_value or ""), re.IGNORECASE)).first
                if suggestion.count() == 0:
                    suggestion = modal.get_by_text(action.target_value or "", exact=False).first
            if suggestion.count():
                suggestion.click(timeout=_OPTION_CLICK_TIMEOUT_MS)
                page.wait_for_timeout(_POST_SUGGESTION_WAIT_MS)
                return True
            return False
    except Exception:
        logger.debug(
            "Easy Apply probe action failed",
            extra={
                "element_id": element.element_id,
                "label": element.label,
                "control_type": element.control_type,
                "action": action.model_dump(mode="json"),
            },
            exc_info=True,
        )
        return False

    return False
