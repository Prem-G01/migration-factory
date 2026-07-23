"""Configuration Engine.

Single source of truth for runtime configuration. Nothing in this platform
should read `os.environ` directly outside this module — that's how you end
up with undocumented, untestable, scattered configuration. Every setting is
declared, typed, defaulted (or required), and validated here.

Precedence (highest wins): environment variables > `.env` file > field
defaults. Nested settings use `__` as the delimiter, e.g.
`MF_LOGGING__LEVEL=DEBUG`.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class LogFormat(StrEnum):
    JSON = "json"
    CONSOLE = "console"


class LoggingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MF_LOGGING__")

    level: str = Field(default="INFO", description="Python logging level name.")
    format: LogFormat = Field(default=LogFormat.JSON)
    include_trace_id: bool = Field(default=True)

    @field_validator("level")
    @classmethod
    def _validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"Invalid log level {v!r}; expected one of {sorted(valid)}")
        return upper


class PluginSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MF_PLUGINS__")

    parser_entrypoint_group: str = Field(default="migration_factory.parsers")
    mapper_entrypoint_group: str = Field(default="migration_factory.mappers")
    fail_fast_on_load_error: bool = Field(
        default=False,
        description=(
            "If True, a single broken plugin aborts startup. If False (default), "
            "the broken plugin is logged and skipped so the platform stays usable."
        ),
    )


class ParsingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MF_PARSING__")

    max_input_file_size_mb: int = Field(default=256, ge=1, le=4096)
    fail_on_unsupported_resource: bool = Field(
        default=False,
        description=(
            "If True, encountering a resource type with no registered mapper is a "
            "hard failure. If False, it is recorded as a warning in the parse "
            "report and the run continues (recommended for discovery/migration-"
            "planning runs against large, messy real-world estates)."
        ),
    )


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MF_DATABASE__")

    url: str = Field(
        default="postgresql+asyncpg://mf_user:mf_pass@localhost:5432/migration_factory",
        description=(
            "Async SQLAlchemy connection string for the API's run store. "
            "In docker-compose, the api service overrides this to point at "
            "the db service (host 'db') via MF_DATABASE__URL."
        ),
    )


class Settings(BaseSettings):
    """Root settings object. Construct via `Settings()` — pydantic-settings
    resolves environment variables, `.env`, and defaults automatically.
    """

    model_config = SettingsConfigDict(
        env_prefix="MF_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    environment: Environment = Field(default=Environment.DEV)
    service_name: str = Field(default="migration-factory")
    data_dir: Path = Field(default=Path("./data"))

    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    plugins: PluginSettings = Field(default_factory=PluginSettings)
    parsing: ParsingSettings = Field(default_factory=ParsingSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PROD


_settings_singleton: Settings | None = None


def get_settings(*, force_reload: bool = False) -> Settings:
    """Process-wide settings accessor.

    A module-level singleton is intentional here (configuration is read-mostly
    and process-scoped) — but it is exposed through this function, never
    imported as a bare global, so tests can call `force_reload=True` with
    monkeypatched env vars instead of fighting import-time caching.
    """
    global _settings_singleton
    if _settings_singleton is None or force_reload:
        _settings_singleton = Settings()
    return _settings_singleton
