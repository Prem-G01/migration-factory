"""Cloud Capability Matrix loading & validation.

The matrix is DATA (versioned JSON), not code: mapping decisions are
reviewable in a diff, testable in isolation, and overridable per-organization
without touching the platform. `load_matrix(path=...)` accepts an external
file so an enterprise can ship its own curated matrix; `load_builtin_matrix`
serves the packaged defaults.

Everything is validated at load time — a malformed matrix must fail the run
before any translation happens, never mid-run.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from migration_factory.core.exceptions import TranslationError
from migration_factory.core.logging import get_logger
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.translation.models import TranslationRule

logger = get_logger(__name__)


class CapabilityMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    matrix_version: str
    source_provider: CloudProvider
    target_provider: CloudProvider
    rules: tuple[TranslationRule, ...] = Field(default_factory=tuple)

    def rule_for(self, canonical_type: CanonicalResourceType) -> TranslationRule | None:
        for rule in self.rules:
            if rule.canonical_type is canonical_type:
                return rule
        return None


def _validate_no_duplicate_types(matrix: CapabilityMatrix, source_name: str) -> None:
    seen: set[CanonicalResourceType] = set()
    for rule in matrix.rules:
        if rule.canonical_type in seen:
            raise TranslationError(
                f"Capability matrix contains duplicate rules for {rule.canonical_type.value!r}",
                context={"matrix_source": source_name, "canonical_type": rule.canonical_type.value},
                remediation="Each canonical type may appear at most once per matrix; "
                "merge or remove the duplicate rule.",
            )
        seen.add(rule.canonical_type)


def _parse_matrix(raw: dict[str, Any], source_name: str) -> CapabilityMatrix:
    try:
        matrix = CapabilityMatrix.model_validate(raw)
    except PydanticValidationError as exc:
        raise TranslationError(
            f"Capability matrix failed schema validation: {source_name}",
            context={"matrix_source": source_name, "validation_errors": exc.errors()},
            remediation="Fix the listed fields; every rule requires canonical_type, "
            "target_service, status, a real rationale, and complexity_weight 1-10.",
            cause=exc,
        ) from exc
    _validate_no_duplicate_types(matrix, source_name)
    logger.info(
        "capability_matrix_loaded",
        matrix_source=source_name,
        matrix_version=matrix.matrix_version,
        source_provider=matrix.source_provider.value,
        target_provider=matrix.target_provider.value,
        rule_count=len(matrix.rules),
    )
    return matrix


def load_matrix(path: Path) -> CapabilityMatrix:
    """Load an organization-supplied matrix from an external file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TranslationError(
            f"Could not read capability matrix file: {path}",
            context={"path": str(path)},
            remediation="Verify the file exists and is readable.",
            cause=exc,
        ) from exc
    except json.JSONDecodeError as exc:
        raise TranslationError(
            f"Capability matrix file is not valid JSON: {path}",
            context={"path": str(path), "json_error": str(exc)},
            remediation="Fix the JSON syntax error at the indicated position.",
            cause=exc,
        ) from exc
    return _parse_matrix(raw, source_name=str(path))


def load_builtin_matrix(
    source_provider: CloudProvider, target_provider: CloudProvider
) -> CapabilityMatrix:
    """Load a matrix packaged with the platform, keyed by provider pair."""
    filename = f"{source_provider.value}_to_{target_provider.value}.json"
    data_root = resources.files("migration_factory.translation").joinpath("data")
    matrix_file = data_root.joinpath(filename)

    try:
        raw = json.loads(matrix_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        available = sorted(
            entry.name for entry in data_root.iterdir() if entry.name.endswith(".json")
        )
        raise TranslationError(
            f"No built-in capability matrix for {source_provider.value} -> "
            f"{target_provider.value}",
            context={"requested": filename, "available_matrices": available},
            remediation="Supply an external matrix via load_matrix(path=...), or add "
            f"{filename} to migration_factory/translation/data/.",
            cause=exc,
        ) from exc
    return _parse_matrix(raw, source_name=f"builtin:{filename}")
