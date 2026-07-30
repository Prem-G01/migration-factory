"""Sentry error tracking integration. Fully opt-in: does nothing unless
SENTRY_DSN is set, so this is safe to call at startup in every environment,
including ones (tests, local dev, a Render deploy that hasn't configured
Sentry yet) that never set it.
"""

from __future__ import annotations

import os
import re

import sentry_sdk
from sentry_sdk.types import Event, Hint

from migration_factory.core.config import Environment, get_settings
from migration_factory.core.logging import get_logger

logger = get_logger(__name__)

# API keys generated via secrets.token_urlsafe() (see api/auth.py) are long
# base64url strings -- no fixed prefix to anchor on, so match the shape
# instead: 24+ chars of the base64url alphabet.
_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")


def redact_api_keys(text: str) -> str:
    """Removes anything that looks like an API key from an error message."""
    return _TOKEN_RE.sub("[REDACTED_KEY]", text)


def _before_send(event: Event, hint: Hint) -> Event | None:
    exc_info = hint.get("exc_info")
    if exc_info:
        exc_value = exc_info[1]
        status_code = getattr(exc_value, "status_code", None)
        if isinstance(status_code, int) and 400 <= status_code < 500:
            # Client errors (bad input, missing auth) aren't operational
            # problems -- don't spend Sentry's free-tier quota on them.
            return None

    message = event.get("message")
    if isinstance(message, str):
        event["message"] = redact_api_keys(message)

    return event


def init_sentry() -> None:
    sentry_dsn = os.environ.get("SENTRY_DSN")
    environment = get_settings().environment

    if not sentry_dsn:
        if environment is Environment.PROD:
            logger.warning("sentry_not_configured", detail="SENTRY_DSN unset in production; errors won't be tracked")
        else:
            logger.info("sentry_disabled", detail="SENTRY_DSN not set")
        return

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=environment.value,
        traces_sample_rate=0.1 if environment is Environment.PROD else 1.0,
        attach_stacktrace=True,
        before_send=_before_send,
    )
    logger.info("sentry_initialized", environment=environment.value)
