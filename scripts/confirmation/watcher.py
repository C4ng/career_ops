from __future__ import annotations

import argparse
import json
import logging
import time

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.models import DEFAULT_CDP_URL
from app.logging_setup import setup_logging
from scripts.confirmation.ui import run_application_confirmation_ui
from scripts.confirmation.email import run_application_confirmation_email


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch LinkedIn application confirmation emails and update submitted applications."
    )
    parser.add_argument(
        "--sender",
        default="jobs-noreply@linkedin.com",
        help="Email sender used for LinkedIn application confirmations.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Override the configured mailbox lookback window.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=180,
        help="Polling interval when not running in --once mode.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one fetch/process cycle and exit.",
    )
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help="Chrome DevTools Protocol URL for UI-based confirmation checks.",
    )
    parser.add_argument(
        "--skip-email",
        action="store_true",
        help="Skip email-based confirmation checks.",
    )
    parser.add_argument(
        "--skip-ui",
        action="store_true",
        help="Skip LinkedIn UI-based confirmation checks.",
    )
    return parser.parse_args()


def run_application_confirmation_watcher(
    *,
    sender: str = "jobs-noreply@linkedin.com",
    lookback_days: int | None = None,
    interval_seconds: int = 180,
    cdp_url: str = DEFAULT_CDP_URL,
    skip_email: bool = False,
    skip_ui: bool = False,
    once: bool = False,
) -> dict[str, object]:
    log_paths = setup_logging("linkedin_application_confirmation_watcher")
    logger = logging.getLogger(__name__)
    iterations = 0
    last_result: dict[str, object] | None = None

    while True:
        iterations += 1
        logger.info(
            "LinkedIn application confirmation watcher poll started",
            extra={
                "iteration": iterations,
                "sender": sender,
                "lookback_days": lookback_days,
                "interval_seconds": interval_seconds,
                "cdp_url": cdp_url,
                "skip_email": skip_email,
                "skip_ui": skip_ui,
                "once": once,
            },
        )
        last_result = {
            "email": None
            if skip_email
            else run_application_confirmation_email(
                sender=sender,
                lookback_days=lookback_days,
            ),
            "ui": None
            if skip_ui
            else run_application_confirmation_ui(
                cdp_url=cdp_url,
            ),
        }
        logger.info(
            "LinkedIn application confirmation watcher poll completed",
            extra={
                "iteration": iterations,
                "result": last_result,
            },
        )
        if once:
            break
        time.sleep(max(1, interval_seconds))

    return {
        "success": bool(
            last_result
            and all(
                result is None or bool(result.get("success"))
                for result in last_result.values()
            )
        ),
        "iterations": iterations,
        "last_result": last_result,
        "log_path": str(log_paths["latest"]) if log_paths else None,
    }


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            run_application_confirmation_watcher(
                sender=args.sender,
                lookback_days=args.lookback_days,
                interval_seconds=args.interval_seconds,
                cdp_url=args.cdp_url,
                skip_email=args.skip_email,
                skip_ui=args.skip_ui,
                once=args.once,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
