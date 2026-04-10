from __future__ import annotations

import email
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from email.policy import default

from app.services.email import close_imap_client, connect_imap_mailbox
from app.sources.linkedin.alerts.parse import (
    extract_application_confirmation_from_email,
    extract_job_cards_from_email,
)
from app.models import (
    LinkedInApplicationConfirmationFetchResult,
    LinkedInEmailConfig,
    LinkedInEmailFetchResult,
    LinkedInJobCard,
    LinkedInRawEmailMessage,
)

logger = logging.getLogger(__name__)


def _since_date_value(lookback_days: int) -> str:
    return (datetime.now() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")


def _quoted_imap_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _search_criteria(config: LinkedInEmailConfig, since_value: str) -> tuple[str, ...]:
    return (
        "FROM",
        _quoted_imap_string(config.sender),
        "SINCE",
        since_value,
    )


def _parse_email_headers(raw_bytes: bytes) -> email.message.EmailMessage:
    return email.message_from_bytes(raw_bytes, policy=default)


def _header_matches_config(parsed: email.message.EmailMessage, config: LinkedInEmailConfig) -> bool:
    from_address = (parsed.get("From") or "").casefold()
    return config.sender.casefold() in from_address


def _extract_body_parts(message: email.message.EmailMessage) -> tuple[str | None, str | None]:
    text_parts: list[str] = []
    html_parts: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            if part.get_content_disposition() == "attachment":
                continue
            if content_type == "text/plain":
                try:
                    text_parts.append(part.get_content())
                except Exception:
                    continue
            elif content_type == "text/html":
                try:
                    html_parts.append(part.get_content())
                except Exception:
                    continue
    else:
        content_type = message.get_content_type()
        if content_type == "text/plain":
            text_parts.append(message.get_content())
        elif content_type == "text/html":
            html_parts.append(message.get_content())

    text_body = "\n".join(part for part in text_parts if part).strip() or None
    html_body = "\n".join(part for part in html_parts if part).strip() or None
    return text_body, html_body


def _parse_email_message(sequence_id: str, raw_bytes: bytes) -> LinkedInRawEmailMessage:
    parsed = _parse_email_headers(raw_bytes)
    text_body, html_body = _extract_body_parts(parsed)
    return LinkedInRawEmailMessage(
        sequence_id=sequence_id,
        message_id=parsed.get("Message-Id"),
        subject=parsed.get("Subject"),
        from_address=parsed.get("From"),
        received_at=parsed.get("Date"),
        text_body=text_body,
        html_body=html_body,
    )


def _config_fields(config: LinkedInEmailConfig) -> dict[str, object]:
    return {
        "provider": config.provider,
        "host": config.host,
        "port": config.port,
        "mailbox": config.mailbox,
        "username": config.username,
        "sender": config.sender,
        "lookback_days": config.lookback_days,
        "max_messages": config.max_messages,
    }


def _extract_imap_bytes(fetch_data: list[object]) -> bytes | None:
    for item in fetch_data:
        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
            return item[1]
    return None


def _fetch_and_filter_emails(
    config: LinkedInEmailConfig,
    *,
    label: str,
    process_message: Callable[[LinkedInRawEmailMessage], None],
) -> tuple[bool, bool, int, list[LinkedInRawEmailMessage]]:
    client, authenticated, mailbox_selected = connect_imap_mailbox(config)
    try:
        since_value = _since_date_value(config.lookback_days)
        logger.info(
            f"Searching {label}",
            extra={
                "mailbox": config.mailbox,
                "sender": config.sender,
                "since": since_value,
                "max_messages": config.max_messages,
            },
        )
        criteria = _search_criteria(config, since_value)
        status, data = client.search(None, *criteria)
        if status != "OK":
            raise RuntimeError(f"IMAP search failed with status {status}")

        sequence_ids = data[0].split() if data and data[0] else []
        logger.info(f"{label} search result", extra={"matched_message_count": len(sequence_ids)})

        messages: list[LinkedInRawEmailMessage] = []
        matched_message_count = 0

        for raw_sequence_id in reversed(sequence_ids):
            sequence_id = raw_sequence_id.decode("utf-8")
            fetch_status, fetch_data = client.fetch(sequence_id, "(BODY.PEEK[HEADER])")
            if fetch_status != "OK":
                logger.warning(f"Skipping {label} header fetch failure", extra={"sequence_id": sequence_id})
                continue
            header_bytes = _extract_imap_bytes(fetch_data)
            if header_bytes is None:
                logger.warning(f"Skipping {label} with empty header payload", extra={"sequence_id": sequence_id})
                continue
            parsed_headers = _parse_email_headers(header_bytes)
            if not _header_matches_config(parsed_headers, config):
                continue

            matched_message_count += 1
            if len(messages) >= config.max_messages:
                continue

            fetch_status, fetch_data = client.fetch(sequence_id, "(RFC822)")
            if fetch_status != "OK":
                logger.warning(f"Skipping {label} fetch failure", extra={"sequence_id": sequence_id})
                continue
            raw_bytes = _extract_imap_bytes(fetch_data)
            if raw_bytes is None:
                logger.warning(f"Skipping {label} with empty RFC822 payload", extra={"sequence_id": sequence_id})
                continue

            message = _parse_email_message(sequence_id, raw_bytes)
            process_message(message)
            messages.append(message)

        return authenticated, mailbox_selected, matched_message_count, messages
    finally:
        close_imap_client(client)


def fetch_linkedin_job_alert_emails(config: LinkedInEmailConfig) -> LinkedInEmailFetchResult:
    logger.info("Fetching LinkedIn job alert emails", extra={"config": _config_fields(config)})

    try:
        job_cards_by_key: dict[str, LinkedInJobCard] = {}

        def process_message(message: LinkedInRawEmailMessage) -> None:
            logger.debug("Matched LinkedIn email content", extra={"email_content": message.model_dump(mode="json")})
            for job_card in extract_job_cards_from_email(message, config.title_exclude_contains):
                dedupe_key = job_card.linkedin_job_id or job_card.job_url
                if not dedupe_key:
                    continue
                job_cards_by_key.setdefault(dedupe_key, job_card)

        authenticated, mailbox_selected, matched_message_count, messages = _fetch_and_filter_emails(
            config, label="LinkedIn job alert emails", process_message=process_message,
        )

        result = LinkedInEmailFetchResult(
            success=authenticated and mailbox_selected,
            **_config_fields(config),
            authenticated=authenticated,
            mailbox_selected=mailbox_selected,
            matched_message_count=matched_message_count,
            messages=messages,
            job_cards=list(job_cards_by_key.values()),
        )
        logger.info(
            "LinkedIn email fetch result",
            extra={
                "result": {
                    "success": result.success,
                    "matched_message_count": result.matched_message_count,
                    "job_card_count": len(result.job_cards),
                    "authenticated": result.authenticated,
                    "mailbox_selected": result.mailbox_selected,
                }
            },
        )
        return result
    except Exception as exc:
        logger.exception("LinkedIn email fetch failed")
        return LinkedInEmailFetchResult(
            success=False,
            **_config_fields(config),
            error=str(exc),
        )


def fetch_linkedin_application_confirmation_emails(
    config: LinkedInEmailConfig,
) -> LinkedInApplicationConfirmationFetchResult:
    logger.info("Fetching LinkedIn application confirmation emails", extra={"config": _config_fields(config)})

    try:
        confirmations_by_key: dict[str, object] = {}
        kept_messages: list[LinkedInRawEmailMessage] = []

        def process_message(message: LinkedInRawEmailMessage) -> None:
            confirmation = extract_application_confirmation_from_email(message)
            if confirmation is None:
                return
            kept_messages.append(message)
            dedupe_key = confirmation.linkedin_job_id or confirmation.message_id or confirmation.sequence_id
            confirmations_by_key.setdefault(dedupe_key, confirmation)

        authenticated, mailbox_selected, matched_message_count, _all_messages = _fetch_and_filter_emails(
            config, label="LinkedIn application confirmation emails", process_message=process_message,
        )

        result = LinkedInApplicationConfirmationFetchResult(
            success=authenticated and mailbox_selected,
            **_config_fields(config),
            authenticated=authenticated,
            mailbox_selected=mailbox_selected,
            matched_message_count=matched_message_count,
            messages=kept_messages,
            confirmations=list(confirmations_by_key.values()),
        )
        logger.info(
            "LinkedIn application confirmation fetch result",
            extra={
                "result": {
                    "success": result.success,
                    "matched_message_count": result.matched_message_count,
                    "confirmation_count": len(result.confirmations),
                    "authenticated": result.authenticated,
                    "mailbox_selected": result.mailbox_selected,
                }
            },
        )
        return result
    except Exception as exc:
        logger.exception("LinkedIn application confirmation fetch failed")
        return LinkedInApplicationConfirmationFetchResult(
            success=False,
            **_config_fields(config),
            error=str(exc),
        )
