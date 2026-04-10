from __future__ import annotations

import json
import logging

from app.prompts.screening.enrich import (
    JD_ENRICHMENT_RESPONSE_SCHEMA,
    JD_ENRICHMENT_SYSTEM_PROMPT,
    build_jd_enrichment_user_payload,
)
from app.services.llm.config import JDEnrichmentLLMConfig
from app.services.llm import request_structured_chat_completion


logger = logging.getLogger(__name__)


def _parse_jd_enrichments(raw_output_text: str) -> list[dict[str, object]]:
    try:
        parsed = json.loads(raw_output_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Failed to parse LLM enrichment output as JSON: {exc}") from exc
    enrichments = parsed.get("enrichments", [])
    if not isinstance(enrichments, list):
        raise ValueError("enrichments must be a list")
    return enrichments


def enrich_linkedin_job_descriptions(
    llm_config: JDEnrichmentLLMConfig,
    jobs: list[dict[str, object]],
) -> list[dict[str, object]]:
    payload = build_jd_enrichment_user_payload(jobs)
    logger.debug(
        "LinkedIn JD enrichment LLM input",
        extra={
            "system_prompt": JD_ENRICHMENT_SYSTEM_PROMPT,
            "user_input": payload,
            "response_schema": JD_ENRICHMENT_RESPONSE_SCHEMA,
        },
    )
    _, raw_response_payload, raw_output_text = request_structured_chat_completion(
        llm_config,
        system_prompt=JD_ENRICHMENT_SYSTEM_PROMPT,
        user_payload=payload,
        response_schema=JD_ENRICHMENT_RESPONSE_SCHEMA,
        schema_name="linkedin_jd_enrichment_batch",
    )
    logger.debug(
        "LinkedIn JD enrichment LLM output",
        extra={
            "raw_output_text": raw_output_text,
            "raw_response_payload": raw_response_payload,
        },
    )
    return _parse_jd_enrichments(raw_output_text)
