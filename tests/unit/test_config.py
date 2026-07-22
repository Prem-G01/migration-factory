from __future__ import annotations

import pytest

from migration_factory.core.config import Environment, LogFormat, Settings


def test_defaults_are_sane() -> None:
    settings = Settings()
    assert settings.environment is Environment.DEV
    assert settings.logging.level == "INFO"
    assert settings.logging.format is LogFormat.JSON
    assert settings.is_production is False


def test_env_var_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MF_ENVIRONMENT", "prod")
    monkeypatch.setenv("MF_LOGGING__LEVEL", "debug")
    settings = Settings()
    assert settings.environment is Environment.PROD
    assert settings.is_production is True
    assert settings.logging.level == "DEBUG"


def test_invalid_log_level_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MF_LOGGING__LEVEL", "NOT_A_LEVEL")
    with pytest.raises(ValueError, match="Invalid log level"):
        Settings()


def test_stray_prefixed_env_var_is_ignored_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """pydantic-settings only binds env vars that match a declared field name;
    an unrelated var sharing the MF_ prefix (e.g. from another tool sharing
    the namespace) must not crash the process. Extra=forbid governs explicit
    constructor kwargs, not the env source — see test below.
    """
    monkeypatch.setenv("MF_SOME_TYPO_FIELD", "x")
    settings = Settings()
    assert settings.environment is Environment.DEV


def test_unrecognized_constructor_kwarg_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(some_typo_field="x")  # type: ignore[call-arg]
