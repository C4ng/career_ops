from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    retryable: Callable[[Exception], bool],
    backoff_base_seconds: float = 1.0,
    operation_name: str = "operation",
    log: logging.Logger | None = None,
) -> T:
    """Call *fn* up to *max_attempts* times, retrying on retryable exceptions.

    Waits ``backoff_base_seconds * 2 ** (attempt - 1)`` before each retry
    (1 s, 2 s, 4 s, … by default).  Non-retryable exceptions propagate immediately.
    """
    _log = log or logger
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if not retryable(exc):
                raise
            if attempt >= max_attempts:
                _log.warning(
                    "Retryable %s failed after %d attempts, giving up",
                    operation_name,
                    max_attempts,
                    extra={"operation": operation_name, "attempt": attempt, "error": str(exc)},
                )
                raise
            wait = backoff_base_seconds * (2 ** (attempt - 1))
            _log.warning(
                "Retryable %s failed (attempt %d/%d), retrying in %.1fs",
                operation_name,
                attempt,
                max_attempts,
                wait,
                extra={"operation": operation_name, "attempt": attempt, "error": str(exc)},
            )
            time.sleep(wait)
    raise RuntimeError("unreachable")  # pragma: no cover
