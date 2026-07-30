"""Tests for Sentry integration (migration_factory.monitoring.sentry_config)."""

from __future__ import annotations

import pytest

from migration_factory.monitoring.sentry_config import (
    _before_send,
    init_sentry,
    redact_api_keys,
)


def test_redact_api_keys_removes_token_shaped_strings() -> None:
    text = "Error: API key KY6aPDnTxCT-Lqx6DyfnjagPKnwRtpj88pglTM6X6mc was rejected"
    redacted = redact_api_keys(text)
    assert "KY6aPDnTxCT" not in redacted
    assert "[REDACTED_KEY]" in redacted


def test_redact_api_keys_leaves_short_text_alone() -> None:
    text = "Error: run 1234 failed"
    assert redact_api_keys(text) == text


def test_init_sentry_noop_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    init_sentry()  # Must not raise, must not require the sentry_sdk import path


def test_before_send_drops_4xx_client_errors() -> None:
    class _FakeHttpError(Exception):
        status_code = 404

    event = {"message": "not found"}
    hint = {"exc_info": (type(_FakeHttpError()), _FakeHttpError(), None)}
    assert _before_send(event, hint) is None


def test_before_send_keeps_5xx_and_redacts_message() -> None:
    class _FakeServerError(Exception):
        status_code = 500

    event = {"message": "boom: key KY6aPDnTxCT-Lqx6DyfnjagPKnwRtpj88pglTM6X6mc leaked"}
    hint = {"exc_info": (type(_FakeServerError()), _FakeServerError(), None)}
    result = _before_send(event, hint)
    assert result is not None
    assert "KY6aPDnTxCT" not in result["message"]
