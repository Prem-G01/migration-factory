"""Parser Engine — shared interface every input-format parser implements.

A parser's ONLY job is: raw input -> `ParsedResource` (provider-native, still
un-normalized). It must NOT reference the Canonical Model — that coupling
belongs to the Mapper layer. This separation is what lets a new input format
(say, ARM templates) be added by a team that knows nothing about the
Canonical Model, and a new mapping (say, Azure-native -> Canonical) be added
by a team that knows nothing about ARM's file format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.domain.enums import CloudProvider


class ParsedResource(BaseModel):
    """Provider-native resource, exactly as the source system described it —
    no normalization applied yet.
    """

    model_config = ConfigDict(extra="forbid")

    source_provider: CloudProvider
    source_type: str = Field(..., description="e.g. 'aws_instance', 'google_compute_instance'")
    source_identifier: str = Field(..., description="Terraform address, ARN, etc.")
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    raw_depends_on: list[str] = Field(
        default_factory=list,
        description="Source-native dependency identifiers (e.g. Terraform addresses); "
        "resolved to canonical ids later by the Mapper/Dependency layer.",
    )
    source_path: str


class ParseWarning(BaseModel):
    source_identifier: str | None = None
    message: str
    remediation: str | None = None


class ParserResult(BaseModel):
    """Everything a parser produces from one input, including partial-failure
    bookkeeping — a parser run against a messy real-world 400-resource state
    file should return the 395 it understood plus 5 structured warnings, not
    raise and discard all 400.
    """

    model_config = ConfigDict(extra="forbid")

    parser_name: str
    source_path: str
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resources: list[ParsedResource] = Field(default_factory=list)
    warnings: list[ParseWarning] = Field(default_factory=list)

    @property
    def resource_count(self) -> int:
        return len(self.resources)


class BaseParser(ABC):
    """Every parser plugin implements this contract and is registered under
    the `migration_factory.parsers` entry-point group (see pyproject.toml).
    """

    name: str

    @abstractmethod
    def supports(self, source_path: Path) -> bool:
        """Cheap, side-effect-free check: can this parser handle this input?
        Used by the Parser Registry for auto-detection; must not raise.
        """
        raise NotImplementedError

    @abstractmethod
    def parse(self, source_path: Path) -> ParserResult:
        """Parse `source_path` into a `ParserResult`.

        Must raise `migration_factory.core.exceptions.ParserError` (not a bare
        exception) for unrecoverable failures (malformed input, unreadable
        file). Per-resource issues that don't invalidate the whole file
        should be recorded as `ParseWarning`s instead of raised.
        """
        raise NotImplementedError
