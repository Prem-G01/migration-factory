"""Canonical Infrastructure Model.

Per the platform's core design constraint: **no code path ever generates
Terraform (or anything else) directly from a raw input file.** Every input —
regardless of source format or source cloud — is normalized into
`CanonicalResource` instances first. Every downstream engine (dependency,
security, FinOps, compliance, AI, Terraform generation) operates exclusively
on this model. This is the single most important invariant in the platform:
it's what keeps the parser count (N formats) decoupled from the generator
count (M target providers) — N+M work instead of N*M.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from migration_factory.core.exceptions import DependencyGraphError
from migration_factory.domain.enums import (
    CanonicalResourceType,
    CloudProvider,
    ResourceLifecycleState,
)

CANONICAL_MODEL_SCHEMA_VERSION = "1.0.0"


class SourceLocation(BaseModel):
    """Provenance: exactly where this resource came from. Mandatory for audit
    trail, error messages that point somewhere useful, and reproducibility.
    """

    model_config = ConfigDict(frozen=True)

    source_system: str = Field(..., description="e.g. 'terraform_state', 'aws_cli'")
    source_path: str = Field(..., description="File path, API endpoint, or export name")
    source_identifier: str | None = Field(
        default=None, description="e.g. terraform resource address"
    )


class CanonicalResource(BaseModel):
    """A single piece of infrastructure, normalized to the platform's shared
    vocabulary.

    `native_attributes` intentionally retains the full, untouched
    provider-native attribute dict — normalization must never be lossy.
    Typed convenience fields (region, tags, ...) are projections for common
    cross-cutting concerns (security, FinOps, compliance all need tags/region
    without knowing every provider's schema); the source of truth for
    provider-specific detail remains `native_attributes`.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=CANONICAL_MODEL_SCHEMA_VERSION)

    id: str = Field(..., description="Stable canonical id, unique within a graph")
    canonical_type: CanonicalResourceType
    source_provider: CloudProvider
    source_type: str = Field(..., description="Provider-native type, e.g. 'aws_instance'")
    name: str

    region: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)

    # Business metadata (populated by discovery or manually during assessment)
    owner: str | None = Field(default=None, description="Team or individual owning this resource")
    environment: str | None = Field(default=None, description="dev, staging, prod, etc.")
    criticality: str | None = Field(default=None, description="critical, high, medium, low")
    application: str | None = Field(default=None, description="Application or service this resource belongs to")
    cost_center: str | None = Field(default=None, description="Cost allocation tag/code")
    notes: str | None = Field(default=None, description="Free-form notes from discovery or human review")

    depends_on: frozenset[str] = Field(
        default_factory=frozenset,
        description="IDs of other CanonicalResource this resource depends on",
    )

    native_attributes: dict[str, Any] = Field(default_factory=dict)
    source_location: SourceLocation

    lifecycle_state: ResourceLifecycleState = ResourceLifecycleState.DISCOVERED
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Canonical resource id must not be blank")
        return v


class CanonicalInfrastructureGraph(BaseModel):
    """A collection of `CanonicalResource` plus the dependency edges between
    them, with graph operations required by every downstream engine:
    deployment ordering (Terraform apply order), destroy ordering (reverse),
    and cycle detection (a circular dependency is invalid infrastructure and
    must fail loudly *before* Terraform generation, not during `apply`).
    """

    model_config = ConfigDict(extra="forbid")

    resources: dict[str, CanonicalResource] = Field(default_factory=dict)

    def add_resource(self, resource: CanonicalResource) -> None:
        if resource.id in self.resources:
            raise DependencyGraphError(
                f"Duplicate resource id {resource.id!r}",
                context={"resource_id": resource.id},
                remediation="Canonical ids must be unique within a graph; check the "
                "mapper generating this id for collisions.",
            )
        self.resources[resource.id] = resource

    def get_dependents(self, resource_id: str) -> list[str]:
        """Resources that depend ON `resource_id` (reverse edges)."""
        return [r.id for r in self.resources.values() if resource_id in r.depends_on]

    def validate_references(self) -> list[str]:
        """Return ids referenced in `depends_on` that don't exist in the graph.

        Non-fatal by design — dangling references are common mid-migration
        (partial scope, filtered discovery) and are surfaced as a validation
        report finding rather than an exception, matching the platform's
        Validation Engine contract.
        """
        dangling: list[str] = []
        for resource in self.resources.values():
            for dep_id in resource.depends_on:
                if dep_id not in self.resources:
                    dangling.append(dep_id)
        return dangling

    def topological_order(self) -> list[str]:
        """Kahn's algorithm. Returns resource ids in a valid deployment order
        (dependencies before dependents). Raises `DependencyGraphError` on a
        cycle, naming every resource still stuck in the cycle so the error is
        actionable instead of a generic "cycle detected".
        """
        # in_degree[x] = number of dependencies x has that exist in the graph
        # (i.e. count of edges pointing INTO x).
        in_degree: dict[str, int] = dict.fromkeys(self.resources, 0)
        for resource in self.resources.values():
            existing_deps = [d for d in resource.depends_on if d in self.resources]
            in_degree[resource.id] = len(existing_deps)

        ready = sorted([rid for rid, deg in in_degree.items() if deg == 0])
        ordered: list[str] = []

        # Reverse adjacency: for each resource, who depends on it.
        dependents_of: dict[str, list[str]] = {rid: [] for rid in self.resources}
        for resource in self.resources.values():
            for dep_id in resource.depends_on:
                if dep_id in dependents_of:
                    dependents_of[dep_id].append(resource.id)

        while ready:
            current = ready.pop(0)
            ordered.append(current)
            for dependent_id in sorted(dependents_of[current]):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    ready.append(dependent_id)

        if len(ordered) != len(self.resources):
            stuck = sorted(set(self.resources) - set(ordered))
            raise DependencyGraphError(
                "Circular dependency detected — cannot compute a deployment order",
                context={"resources_in_cycle": stuck},
                remediation="Inspect depends_on for the listed resources; one of them "
                "must be broken (often a mis-mapped implicit dependency).",
            )
        return ordered

    def destroy_order(self) -> list[str]:
        """Reverse of deployment order — dependents destroyed before their
        dependencies, matching `terraform destroy` semantics.
        """
        return list(reversed(self.topological_order()))
