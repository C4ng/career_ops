from __future__ import annotations


def object_payload_for_logging(
    item: object,
    *,
    include_keys: list[str] | tuple[str, ...] | None = None,
    exclude_keys: list[str] | tuple[str, ...] | None = None,
) -> dict[str, object]:
    if hasattr(item, "model_dump"):
        payload = item.model_dump(mode="json")  # type: ignore[call-arg]
    elif isinstance(item, dict):
        payload = dict(item)
    else:
        payload = {"value": str(item)}

    if include_keys is not None:
        payload = {key: payload.get(key) for key in include_keys}
    if exclude_keys is not None:
        for key in exclude_keys:
            payload.pop(key, None)
    return payload


def item_examples_for_logging(
    items: list[object],
    *,
    limit: int = 5,
    include_keys: list[str] | tuple[str, ...] | None = None,
    exclude_keys: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, object]]:
    return [
        object_payload_for_logging(item, include_keys=include_keys, exclude_keys=exclude_keys)
        for item in items[:limit]
    ]


def job_card_payload_without_raw_card_text(job_card_payload: dict[str, object]) -> dict[str, object]:
    trimmed = dict(job_card_payload)
    trimmed.pop("raw_card_text", None)
    return trimmed


def collection_result_payload_for_logging(result) -> dict[str, object]:
    payload = result.model_dump(mode="json")
    payload["job_cards"] = [
        job_card_payload_without_raw_card_text(job_card_payload)
        for job_card_payload in payload.get("job_cards", [])
    ]
    return payload


def email_fetch_result_payload_for_logging(result) -> dict[str, object]:
    payload = result.model_dump(mode="json")
    payload.pop("messages", None)
    payload["job_cards"] = [
        job_card_payload_without_raw_card_text(job_card_payload)
        for job_card_payload in payload.get("job_cards", [])
    ]
    return payload
