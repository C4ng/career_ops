from __future__ import annotations

import json
import logging

from app.models import LinkedInJobRankingResult, LinkedInRankingConfig
from app.services.llm.config import RankingLLMConfig
from app.prompts.screening.rank import (
    LINKEDIN_RANKING_RESPONSE_SCHEMA,
    LINKEDIN_RANKING_SYSTEM_PROMPT,
    build_linkedin_ranking_user_payload,
)
from app.services.llm import request_structured_chat_completion


logger = logging.getLogger(__name__)


def _parse_job_rankings(raw_output_text: str) -> list[LinkedInJobRankingResult]:
    try:
        parsed = json.loads(raw_output_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Failed to parse LLM ranking output as JSON: {exc}") from exc
    rankings = parsed.get("rankings", [])
    if not isinstance(rankings, list):
        raise ValueError("rankings must be a list")
    return [LinkedInJobRankingResult.model_validate(item) for item in rankings]


def rank_linkedin_jobs(
    llm_config: RankingLLMConfig,
    ranking_config: LinkedInRankingConfig,
    jobs: list[dict[str, object]],
) -> list[LinkedInJobRankingResult]:
    payload = build_linkedin_ranking_user_payload(ranking_config, jobs)
    logger.debug(
        "LinkedIn ranking LLM input",
        extra={
            "system_prompt": LINKEDIN_RANKING_SYSTEM_PROMPT,
            "user_input": payload,
            "response_schema": LINKEDIN_RANKING_RESPONSE_SCHEMA,
        },
    )
    _, raw_response_payload, raw_output_text = request_structured_chat_completion(
        llm_config,
        system_prompt=LINKEDIN_RANKING_SYSTEM_PROMPT,
        user_payload=payload,
        response_schema=LINKEDIN_RANKING_RESPONSE_SCHEMA,
        schema_name="linkedin_job_ranking_batch",
    )
    logger.debug(
        "LinkedIn ranking LLM output",
        extra={
            "raw_output_text": raw_output_text,
            "raw_response_payload": raw_response_payload,
        },
    )
    return _parse_job_rankings(raw_output_text)
