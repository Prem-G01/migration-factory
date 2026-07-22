"""Migration Assessment models — the answer to "should we migrate this, and
what will hurt?"

Scoring semantics (documented here because ambiguous scores are worse than no
scores): **complexity score, 1-100, higher = harder/riskier.** A score of 82
means "expect significant engineering effort and risk", not "82% ready".
Every score is deterministic and decomposable — the components that produced
it are part of the output, never hidden inside the number.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.domain.enums import CanonicalResourceType
from migration_factory.translation.models import SupportStatus


class MigrationStrategy(StrEnum):
    REHOST = "rehost"  # lift-and-shift; translation is mechanical
    REPLATFORM = "replatform"  # target-side changes required but automatable
    MANUAL = "manual"  # human redesign required


class DowntimeClass(StrEnum):
    NONE = "none"
    LOW = "low"  # seconds to minutes (DNS/traffic cutover)
    MEDIUM = "medium"  # minutes (instance cutover)
    HIGH = "high"  # requires a planned window (stateful data migration)


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ScoreBreakdown(BaseModel):
    """The decomposition of a resource's complexity score. Sum of the parts
    (clamped 1-100) IS the score — no hidden factors.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_complexity: int = Field(..., description="complexity_weight from the matrix rule x 6")
    dependency_load: int = Field(..., description="+4 per dependency edge, capped at 20")
    support_penalty: int = Field(
        ..., description="supported=0, partial=15, manual=30, unsupported=40"
    )


class ResourceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    resource_name: str
    canonical_type: CanonicalResourceType
    complexity_score: int = Field(..., ge=1, le=100)
    score_breakdown: ScoreBreakdown
    support_status: SupportStatus
    strategy: MigrationStrategy
    downtime: DowntimeClass
    dependency_count: int
    blockers: list[str] = Field(
        default_factory=list,
        description="Manual actions and structural issues that gate this resource's migration",
    )


class MigrationPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_number: int
    name: str
    resource_ids: list[str] = Field(default_factory=list)


class MigrationAssessment(BaseModel):
    """Estate-level assessment: overall score, risk, blockers, phased plan."""

    model_config = ConfigDict(extra="forbid")

    overall_complexity_score: int = Field(..., ge=1, le=100)
    risk_level: RiskLevel
    resource_assessments: list[ResourceAssessment] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    phases: list[MigrationPhase] = Field(default_factory=list)
    recommendation: str


class BusinessImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affected_applications: list[str] = Field(default_factory=list)
    affected_teams: list[str] = Field(default_factory=list)
    critical_resource_count: int = 0
    estimated_user_impact: str = ""
    revenue_risk: str = "low"


class TechnicalDebt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[str] = Field(default_factory=list)
    modernization_opportunities: list[str] = Field(default_factory=list)
    debt_score: int = Field(default=0, ge=0, le=100, description="Higher = more debt")


class ReadinessAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_readiness: str = Field(default="not_ready", description="ready, partially_ready, not_ready")
    checklist: dict[str, bool] = Field(default_factory=dict)
    blockers_remaining: int = 0
    readiness_score: int = Field(default=0, ge=0, le=100)
