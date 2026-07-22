"""Translation layer models.

Two non-negotiable design rules encoded in these schemas:

1. **Rule-based, not AI-generated.** A `TranslationRule` is deterministic
   data (loaded from a versioned JSON capability matrix), reviewed by humans,
   diffable in PRs. The AI layer (later phases) consumes and explains these
   rules; it never invents mappings.
2. **Explainability is a schema field, not a feature.** `rationale` is
   REQUIRED on every rule. A translation decision that cannot state why it
   was made is rejected at load time — this is how "why was Cloud SQL
   selected?" is answerable for every resource, always, without post-hoc
   generation.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from migration_factory.domain.enums import CanonicalResourceType, CloudProvider


class SupportStatus(StrEnum):
    """How completely a source resource translates to the target provider."""

    SUPPORTED = "supported"  # clean 1:1 or near-1:1 mapping
    PARTIAL = "partial"  # mapping exists but with semantic differences
    MANUAL = "manual"  # mapping requires human redesign
    UNSUPPORTED = "unsupported"  # no target equivalent / no rule registered


class TranslationRule(BaseModel):
    """One row of the Cloud Capability Matrix: how a canonical resource type
    translates from one provider to another.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_type: CanonicalResourceType
    target_service: str = Field(..., description="Human name, e.g. 'Compute Engine'")
    target_terraform_types: list[str] = Field(
        default_factory=list,
        description="Terraform resource types the generator will emit, e.g. "
        "['google_compute_instance']. A single source resource may fan out to "
        "several target resources (e.g. AWS ALB -> forwarding rule + proxy + "
        "URL map + backend service).",
    )
    status: SupportStatus
    required_changes: list[str] = Field(
        default_factory=list,
        description="Semantic differences that MUST be handled in generation "
        "(automatable, but not identity mappings).",
    )
    manual_actions: list[str] = Field(
        default_factory=list,
        description="Actions a human must perform; these become assessment blockers.",
    )
    rationale: str = Field(
        ..., min_length=10, description="WHY this mapping. Mandatory — see module docstring."
    )
    complexity_weight: int = Field(
        ..., ge=1, le=10, description="Relative migration difficulty, feeds assessment scoring."
    )

    @field_validator("rationale")
    @classmethod
    def _rationale_not_placeholder(cls, v: str) -> str:
        if v.strip().lower() in {"tbd", "todo", "n/a", "none"}:
            raise ValueError("rationale must be a real explanation, not a placeholder")
        return v


class TranslationResult(BaseModel):
    """The translation decision for ONE canonical resource, with full
    provenance back to the rule that produced it.
    """

    model_config = ConfigDict(extra="forbid")

    resource_id: str
    resource_name: str
    canonical_type: CanonicalResourceType
    status: SupportStatus
    target_service: str | None = None
    target_terraform_types: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    manual_actions: list[str] = Field(default_factory=list)
    rationale: str


class TranslationReport(BaseModel):
    """Translation decisions for an entire canonical graph."""

    model_config = ConfigDict(extra="forbid")

    source_provider: CloudProvider
    target_provider: CloudProvider
    results: list[TranslationResult] = Field(default_factory=list)

    def by_status(self, status: SupportStatus) -> list[TranslationResult]:
        return [r for r in self.results if r.status is status]

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in SupportStatus}
        for result in self.results:
            counts[result.status.value] += 1
        return counts
