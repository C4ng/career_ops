"""Resolve answers for application questions — candidate dossier lookup + LLM."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

from app.application.easy_apply.parse import normalize_apply_text
from app.prompts.application.question_mapping import (
    APPLICATION_QUESTION_MAPPING_RESPONSE_SCHEMA,
    APPLICATION_QUESTION_MAPPING_SYSTEM_PROMPT,
    build_application_question_mapping_user_payload,
)
from app.models import (
    LinkedInApplicationAnswerProposal,
    LinkedInApplicationQuestion,
    LinkedInCandidateDossier,
)
from app.services.llm.config import ApplicationQuestionMappingLLMConfig
from app.services.llm import request_structured_chat_completion


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Candidate dossier label → value lookup
# ---------------------------------------------------------------------------

# Resolver signature: (dossier, normalized_label) -> str | None
_Resolver = Callable[[LinkedInCandidateDossier, str], str | None]

# Each entry is (set_of_trigger_substrings, resolver).
# The first rule whose trigger set has ANY member contained in the normalized
# label wins; the resolver is then called with (dossier, normalized_label).
_LABEL_RULES: list[tuple[frozenset[str], _Resolver]] = [
    (
        frozenset({"first name"}),
        lambda d, _lbl: d.contact.first_name,
    ),
    (
        frozenset({"last name", "surname"}),
        lambda d, _lbl: d.contact.last_name,
    ),
    (
        frozenset({"email"}),
        lambda d, _lbl: d.contact.email,
    ),
    (
        frozenset({"phone", "mobile", "telephone"}),
        lambda d, _lbl: d.contact.phone,
    ),
    (
        frozenset({"city", "location"}),
        lambda d, _lbl: d.contact.city,
    ),
    (
        frozenset({"country", "code pays", "phone country"}),
        lambda d, _lbl: (
            d.contact.phone_country_label
            or d.work_authorization.work_country
            or d.contact.country
        ),
    ),
    (
        frozenset({"salary"}),
        lambda d, _lbl: (
            str(d.application_preferences.desired_salary).split()[0]
            if d.application_preferences.desired_salary
            else None
        ),
    ),
    (
        frozenset({"notice period", "how much notice", "start date"}),
        lambda d, _lbl: (
            str(d.application_preferences.notice_period)
            if d.application_preferences.notice_period is not None
            else None
        ),
    ),
    (
        frozenset({"headline", "summary"}),
        lambda d, _lbl: d.experience.summary,
    ),
]


def resolve_candidate_value_for_label(
    dossier: LinkedInCandidateDossier,
    label: str | None,
) -> str | None:
    normalized_label = normalize_apply_text(label)
    if not normalized_label:
        return None

    for triggers, resolver in _LABEL_RULES:
        if any(trigger in normalized_label for trigger in triggers):
            return resolver(dossier, normalized_label)

    return None


# ---------------------------------------------------------------------------
# Deterministic dossier resolution
# ---------------------------------------------------------------------------

def _match_option_from_dossier(
    dossier: LinkedInCandidateDossier,
    question: LinkedInApplicationQuestion,
) -> LinkedInApplicationAnswerProposal | None:
    answer_value = resolve_candidate_value_for_label(dossier, question.prompt_text)

    if not answer_value:
        return None

    if question.options:
        normalized_options = {normalize_apply_text(option): option for option in question.options}
        normalized_answer = normalize_apply_text(answer_value)
        resolved_option = normalized_options.get(normalized_answer)
        if resolved_option is None:
            for option in question.options:
                if normalized_answer in normalize_apply_text(option):
                    resolved_option = option
                    break
        if resolved_option is None:
            return None
        answer_value = resolved_option

    return LinkedInApplicationAnswerProposal(
        question_key=question.question_key,
        answer_source="deterministic",
        answer_value=answer_value,
        confidence="high",
        requires_user_input=False,
        reason="Resolved from candidate dossier override.",
    )


def resolve_questions_from_dossier(
    dossier: LinkedInCandidateDossier,
    questions: list[LinkedInApplicationQuestion],
) -> tuple[list[LinkedInApplicationAnswerProposal], list[LinkedInApplicationQuestion]]:
    resolved: list[LinkedInApplicationAnswerProposal] = []
    unresolved: list[LinkedInApplicationQuestion] = []
    for question in questions:
        proposal = _match_option_from_dossier(dossier, question)
        if proposal is None:
            unresolved.append(question)
            continue
        resolved.append(proposal)
    return resolved, unresolved


# ---------------------------------------------------------------------------
# LLM-backed resolution
# ---------------------------------------------------------------------------

def _parse_question_mapping_output(raw_output_text: str) -> list[LinkedInApplicationAnswerProposal]:
    parsed = json.loads(raw_output_text)
    proposals = parsed.get("proposals", [])
    if not isinstance(proposals, list):
        raise ValueError("proposals must be a list")
    return [LinkedInApplicationAnswerProposal.model_validate(item) for item in proposals]


def map_questions_with_llm(
    llm_config: ApplicationQuestionMappingLLMConfig,
    dossier: LinkedInCandidateDossier,
    questions: list[LinkedInApplicationQuestion],
    *,
    job_context: dict[str, object] | None = None,
) -> list[LinkedInApplicationAnswerProposal]:
    _, _, _, proposals = map_questions_with_llm_debug(
        llm_config,
        dossier,
        questions,
        job_context=job_context,
    )
    return proposals


def map_questions_with_llm_debug(
    llm_config: ApplicationQuestionMappingLLMConfig,
    dossier: LinkedInCandidateDossier,
    questions: list[LinkedInApplicationQuestion],
    *,
    job_context: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object], str, list[LinkedInApplicationAnswerProposal]]:
    if not questions:
        return {}, {}, "{}", []

    resolved_proposals, unresolved_questions = resolve_questions_from_dossier(dossier, questions)
    if not unresolved_questions:
        return {}, {}, "{}", resolved_proposals

    payload = build_application_question_mapping_user_payload(
        dossier,
        unresolved_questions,
        job_context=job_context,
    )
    logger.debug(
        "Application question-mapping LLM input",
        extra={
            "system_prompt": APPLICATION_QUESTION_MAPPING_SYSTEM_PROMPT,
            "user_input": payload,
            "response_schema": APPLICATION_QUESTION_MAPPING_RESPONSE_SCHEMA,
        },
    )
    _, raw_response_payload, raw_output_text = request_structured_chat_completion(
        llm_config,
        system_prompt=APPLICATION_QUESTION_MAPPING_SYSTEM_PROMPT,
        user_payload=payload,
        response_schema=APPLICATION_QUESTION_MAPPING_RESPONSE_SCHEMA,
        schema_name="job_application_question_mapping",
    )
    logger.debug(
        "Application question-mapping LLM output",
        extra={
            "raw_output_text": raw_output_text,
            "raw_response_payload": raw_response_payload,
        },
    )
    llm_proposals = _parse_question_mapping_output(raw_output_text)
    return payload, raw_response_payload, raw_output_text, [*resolved_proposals, *llm_proposals]
