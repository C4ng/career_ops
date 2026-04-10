from __future__ import annotations

import json
import logging
import os
import time

import httpx

from app.services.llm.config import LLMServiceConfig
from app.utils.retry import retry_with_backoff


logger = logging.getLogger(__name__)


def _extract_content(response_payload: dict[str, object], *, schema_name: str) -> str:
    """Extract text content from a chat completion response, with clear error messages."""
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        raise ValueError(
            f"LLM response for '{schema_name}' has no choices. "
            f"Keys present: {list(response_payload.keys())}"
        )

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError(
            f"LLM response for '{schema_name}' choices[0] is not a dict: {type(first_choice)}"
        )

    finish_reason = first_choice.get("finish_reason")
    if finish_reason not in ("stop", None):
        logger.warning(
            "LLM completion finished with non-stop reason",
            extra={"schema_name": schema_name, "finish_reason": finish_reason},
        )

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError(
            f"LLM response for '{schema_name}' choices[0].message is missing or not a dict. "
            f"finish_reason={finish_reason!r}"
        )

    content = message.get("content")
    if content is None:
        raise ValueError(
            f"LLM response for '{schema_name}' choices[0].message.content is None. "
            f"finish_reason={finish_reason!r}, message keys: {list(message.keys())}"
        )
    if not isinstance(content, str):
        raise ValueError(
            f"LLM response for '{schema_name}' content is not a string: {type(content)}"
        )

    return content


def _usage_summary(response_payload: dict[str, object]) -> dict[str, object] | None:
    usage = response_payload.get("usage")
    if not isinstance(usage, dict):
        return None
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "prompt_tokens_details": usage.get("prompt_tokens_details"),
        "completion_tokens_details": usage.get("completion_tokens_details"),
    }


def _choice_finish_reasons(response_payload: dict[str, object]) -> list[object]:
    choices = response_payload.get("choices")
    if not isinstance(choices, list):
        return []
    return [choice.get("finish_reason") for choice in choices if isinstance(choice, dict)]


def _is_retryable_llm_error(exc: Exception) -> bool:
    """Return True for transient LLM API errors worth retrying."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return False


def request_structured_chat_completion(
    config: LLMServiceConfig,
    *,
    system_prompt: str,
    user_payload: dict[str, object],
    response_schema: dict[str, object],
    schema_name: str,
    max_attempts: int = 3,
) -> tuple[dict[str, object], dict[str, object], str]:
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable: {config.api_key_env}")

    request_payload = {
        "model": config.model,
        "temperature": config.temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": response_schema,
            },
        },
    }

    request_payload_json = json.dumps(request_payload, ensure_ascii=False)
    user_payload_json = json.dumps(user_payload, ensure_ascii=False)
    started_at = time.perf_counter()
    response: httpx.Response | None = None
    try:
        def _do_request() -> dict[str, object]:
            nonlocal response
            with httpx.Client(timeout=config.timeout_seconds) as client:
                response = client.post(
                    f"{config.api_base.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                )
                response.raise_for_status()
                return response.json()

        response_payload = retry_with_backoff(
            _do_request,
            max_attempts=max_attempts,
            retryable=_is_retryable_llm_error,
            operation_name=f"llm/{schema_name}",
            log=logger,
        )
    except Exception:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
        logger.exception(
            "LLM structured chat completion failed",
            extra={
                "llm_call": {
                    "provider": config.provider,
                    "model": config.model,
                    "schema_name": schema_name,
                    "api_base": config.api_base,
                    "timeout_seconds": config.timeout_seconds,
                    "status_code": response.status_code if response is not None else None,
                    "duration_ms": duration_ms,
                    "system_prompt_chars": len(system_prompt),
                    "user_payload_chars": len(user_payload_json),
                    "request_payload_chars": len(request_payload_json),
                    "approx_request_tokens": round(len(request_payload_json) / 4),
                }
            },
        )
        raise

    content = _extract_content(response_payload, schema_name=schema_name)
    response_payload_json = json.dumps(response_payload, ensure_ascii=False)
    duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
    logger.info(
        "LLM structured chat completion completed",
        extra={
            "llm_call": {
                "provider": config.provider,
                "model": config.model,
                "schema_name": schema_name,
                "api_base": config.api_base,
                "timeout_seconds": config.timeout_seconds,
                "status_code": response.status_code if response is not None else None,
                "duration_ms": duration_ms,
                "system_prompt_chars": len(system_prompt),
                "user_payload_chars": len(user_payload_json),
                "request_payload_chars": len(request_payload_json),
                "response_payload_chars": len(response_payload_json),
                "raw_output_chars": len(content),
                "approx_request_tokens": round(len(request_payload_json) / 4),
                "approx_response_tokens": round(len(content) / 4),
                "usage": _usage_summary(response_payload),
                "finish_reasons": _choice_finish_reasons(response_payload),
            }
        },
    )
    return request_payload, response_payload, content
