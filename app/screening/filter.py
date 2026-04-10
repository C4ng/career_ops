from __future__ import annotations

import json
import logging

from app.models import (
    LinkedInTitleTriageCandidate,
    LinkedInTitleTriageConfig,
    LinkedInTitleTriageDecision,
)
from app.services.llm.config import TitleTriageLLMConfig
from app.prompts.screening.triage import (
    TITLE_TRIAGE_RESPONSE_SCHEMA,
    TITLE_TRIAGE_SYSTEM_PROMPT,
    build_title_triage_user_payload,
)
from app.services.llm import request_structured_chat_completion


logger = logging.getLogger(__name__)


def _parse_title_triage_decisions(raw_output_text: str) -> list[LinkedInTitleTriageDecision]:
    try:
        parsed = json.loads(raw_output_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Failed to parse LLM triage output as JSON: {exc}") from exc
    return [
        LinkedInTitleTriageDecision.model_validate(item)
        for item in parsed.get("decisions", [])
    ]


def triage_linkedin_job_titles(
    llm_config: TitleTriageLLMConfig,
    triage_config: LinkedInTitleTriageConfig,
    candidates: list[LinkedInTitleTriageCandidate],
) -> list[LinkedInTitleTriageDecision]:
    payload = build_title_triage_user_payload(triage_config, candidates)
    logger.debug(
        "LinkedIn title triage LLM input",
        extra={
            "system_prompt": TITLE_TRIAGE_SYSTEM_PROMPT,
            "user_input": payload,
            "response_schema": TITLE_TRIAGE_RESPONSE_SCHEMA,
        },
    )
    _, raw_response_payload, raw_output_text = request_structured_chat_completion(
        llm_config,
        system_prompt=TITLE_TRIAGE_SYSTEM_PROMPT,
        user_payload=payload,
        response_schema=TITLE_TRIAGE_RESPONSE_SCHEMA,
        schema_name="linkedin_title_triage_batch",
    )
    logger.debug(
        "LinkedIn title triage LLM output",
        extra={
            "raw_output_text": raw_output_text,
            "raw_response_payload": raw_response_payload,
        },
    )
    return _parse_title_triage_decisions(raw_output_text)
