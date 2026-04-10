from __future__ import annotations

import logging

from app.services.email import close_imap_client, connect_imap_mailbox
from app.models import (
    LinkedInEmailConfig,
    LinkedInEmailConnectionResult,
)

logger = logging.getLogger(__name__)


def verify_linkedin_email_connection(
    config: LinkedInEmailConfig,
) -> LinkedInEmailConnectionResult:
    logger.info(
        "Verifying LinkedIn email connection",
        extra={
            "config": {
                "provider": config.provider,
                "host": config.host,
                "port": config.port,
                "mailbox": config.mailbox,
                "username": config.username,
                "password_env": config.password_env,
                "sender": config.sender,
                "lookback_days": config.lookback_days,
                "max_messages": config.max_messages,
            }
        },
    )

    client = None
    try:
        client, authenticated, mailbox_selected = connect_imap_mailbox(config)

        result = LinkedInEmailConnectionResult(
            success=authenticated and mailbox_selected,
            provider=config.provider,
            host=config.host,
            port=config.port,
            mailbox=config.mailbox,
            username=config.username,
            sender=config.sender,
            lookback_days=config.lookback_days,
            max_messages=config.max_messages,
            authenticated=authenticated,
            mailbox_selected=mailbox_selected,
        )
        logger.info(
            "LinkedIn email connection result",
            extra={"result": result.model_dump(mode="json")},
        )
        return result
    except Exception as exc:
        logger.exception("LinkedIn email connection failed")
        return LinkedInEmailConnectionResult(
            success=False,
            provider=config.provider,
            host=config.host,
            port=config.port,
            mailbox=config.mailbox,
            username=config.username,
            sender=config.sender,
            lookback_days=config.lookback_days,
            max_messages=config.max_messages,
            error=str(exc),
        )
    finally:
        close_imap_client(client)
