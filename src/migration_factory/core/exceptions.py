"""Exception hierarchy for the Migration Factory platform.

Design rules (enforced by review, not just convention):

1. Every raised exception MUST carry machine-readable `context` — never rely on
   the message string alone. Downstream (logging, AI root-cause analysis,
   audit trail) consumes `context`, not `str(exc)`.
2. Every exception MUST carry a stable `error_code` so alerting/runbooks can
   pattern-match on it instead of parsing free text.
3. Where a corrective action exists, it MUST be surfaced via `remediation` —
   this is what turns an error into an actionable message instead of a stack
   trace, and it's what the AI Engine reads to propose fixes automatically.
"""

from __future__ import annotations

from typing import Any


class MigrationFactoryError(Exception):
    """Base class for every exception raised inside the platform.

    Attributes:
        error_code: Stable, greppable identifier, e.g. "PARSER_INVALID_FORMAT".
        context: Structured data describing what was being processed when the
            error occurred (file path, resource id, line number, etc).
        remediation: Optional human-readable corrective action.
    """

    error_code: str = "MIGRATION_FACTORY_ERROR"

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        remediation: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}
        self.remediation = remediation
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> dict[str, Any]:
        """Serialize for structured logging / audit trail / API error responses."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
            "remediation": self.remediation,
        }

    def __str__(self) -> str:
        base = f"[{self.error_code}] {self.message}"
        if self.context:
            base += f" | context={self.context}"
        if self.remediation:
            base += f" | remediation={self.remediation}"
        return base


class ConfigurationError(MigrationFactoryError):
    """Raised for invalid, missing, or conflicting configuration."""

    error_code = "CONFIGURATION_ERROR"


class PluginError(MigrationFactoryError):
    """Raised when a plugin fails to load, register, or validate its interface."""

    error_code = "PLUGIN_ERROR"


class ParserError(MigrationFactoryError):
    """Raised when a parser cannot process its input.

    Recoverable by design: callers may catch this per-resource and continue
    processing the remainder of a file, recording the failure for the report
    rather than aborting the whole run.
    """

    error_code = "PARSER_ERROR"


class UnsupportedResourceError(ParserError):
    """Raised (or recorded as a warning) when a resource type has no parser/mapper.

    This is intentionally a *distinct* class from ParserError so callers can
    choose to treat "unsupported" as a soft warning (continue, report) while
    treating malformed input as hard failures (abort).
    """

    error_code = "UNSUPPORTED_RESOURCE"


class MappingError(MigrationFactoryError):
    """Raised when a parsed provider-native resource cannot be normalized
    into the Canonical Infrastructure Model.
    """

    error_code = "MAPPING_ERROR"


class DependencyGraphError(MigrationFactoryError):
    """Raised for graph integrity violations: cycles, dangling references, etc."""

    error_code = "DEPENDENCY_GRAPH_ERROR"


class ValidationError(MigrationFactoryError):
    """Raised when a Canonical Resource or generated artifact fails validation."""

    error_code = "VALIDATION_ERROR"


class TranslationError(MigrationFactoryError):
    """Raised when the Translation Engine cannot operate: missing capability
    matrix for a provider pair, malformed matrix data, or mixed-provider
    graphs passed where a single source provider is required.
    """

    error_code = "TRANSLATION_ERROR"
