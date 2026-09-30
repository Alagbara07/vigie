"""Correlation fields for OAuth diagnostic logs.

The attempt id is a short hash of the OAuth state so a connect request and its
callback can be matched. The state token itself is never written to the log.
"""

import hashlib
import logging
import traceback
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("vigie_oauth_request_id", default="-")
_attempt_id: ContextVar[str] = ContextVar("vigie_oauth_attempt_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def attempt_id(state: str) -> str:
    cleaned = state.strip()
    if not cleaned:
        return "absent"
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12]


def bind(request_id: str, attempt: str) -> None:
    _request_id.set(request_id)
    _attempt_id.set(attempt)


def prefix() -> str:
    if _request_id.get() == "-" and _attempt_id.get() == "-":
        return ""
    return f"request={_request_id.get()} attempt={_attempt_id.get()} "


def log_exception(logger: logging.Logger, category: str, exc: BaseException) -> None:
    """Log the exception type and stack, not the exception text.

    Provider and database messages can contain tokens, mailbox addresses, or
    SQL parameters. The stack frames are source lines only.
    """

    frames = "".join(traceback.format_tb(exc.__traceback__)).rstrip()
    logger.warning(
        "%sMicrosoft OAuth exception category=%s error_type=%s\n%s",
        prefix(),
        category,
        type(exc).__name__,
        frames,
    )
