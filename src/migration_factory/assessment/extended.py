"""Extended assessment capabilities: business impact analysis, technical debt
analysis, readiness assessment, Mermaid dependency visualization, and
platform version management.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.assessment.models import (
    BusinessImpact,
    MigrationAssessment,
    MigrationStrategy,
    ReadinessAssessment,
    TechnicalDebt,
)
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.domain.enums import CanonicalResourceType
from migration_factory.translation.models import SupportStatus, TranslationReport

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Business Impact Analysis
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BusinessImpactAnalyzer:
    """Analyzes the business impact of a migration based on resource metadata."""

    def analyze(
        self,
        graph: CanonicalInfrastructureGraph,
        assessment: MigrationAssessment,
    ) -> BusinessImpact:
        applications: set[str] = set()
        teams: set[str] = set()
        critical_count = 0

        for resource in graph.resources.values():
            if resource.application:
                applications.add(resource.application)
            if resource.owner:
                teams.add(resource.owner)
            if resource.criticality in {"critical", "high"}:
                critical_count += 1

        # Infer revenue risk from criticality
        if critical_count > 3:
            revenue_risk = "high"
            user_impact = f"{critical_count} critical/high resources at risk — potential service disruption"
        elif critical_count > 0:
            revenue_risk = "medium"
            user_impact = f"{critical_count} critical/high resources — limited disruption expected"
        else:
            revenue_risk = "low"
            user_impact = "No critical resources identified — minimal user impact"

        return BusinessImpact(
            affected_applications=sorted(applications),
            affected_teams=sorted(teams),
            critical_resource_count=critical_count,
            estimated_user_impact=user_impact,
            revenue_risk=revenue_risk,
        )


# ---------------------------------------------------------------------------
# Technical Debt Analysis
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TechnicalDebtAnalyzer:
    """Identifies technical debt and modernization opportunities."""

    def analyze(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
    ) -> TechnicalDebt:
        issues: list[str] = []
        opportunities: list[str] = []

        for resource in graph.resources.values():
            attrs = resource.native_attributes

            # Instance sizing debt
            if resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                instance_type = str(attrs.get("instance_type", ""))
                if instance_type.startswith("m5.4x") or instance_type.startswith("r5.4x"):
                    issues.append(f"{resource.name}: oversized instance ({instance_type})")
                if not attrs.get("monitoring"):
                    issues.append(f"{resource.name}: no detailed monitoring enabled")

            # Unencrypted storage
            if resource.canonical_type is CanonicalResourceType.STORAGE_OBJECT_BUCKET:
                if not attrs.get("server_side_encryption_configuration"):
                    issues.append(f"{resource.name}: no encryption at rest")

            # Missing tags
            if not resource.tags:
                issues.append(f"{resource.name}: no tags/labels — untrackable for cost allocation")

        # Modernization opportunities from translation
        for tr in translation.results:
            if tr.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                opportunities.append(f"{tr.resource_name}: consider containerizing to Cloud Run or GKE")
            if tr.canonical_type is CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION:
                opportunities.append(f"{tr.resource_name}: evaluate Cloud Run as an alternative to Cloud Functions")

        # Score: higher = more debt
        debt_score = min(100, len(issues) * 8)

        return TechnicalDebt(
            issues=issues[:20],
            modernization_opportunities=opportunities[:10],
            debt_score=debt_score,
        )


# ---------------------------------------------------------------------------
# Readiness Assessment
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ReadinessAssessor:
    """Evaluates whether a migration is ready to proceed."""

    def assess(
        self,
        graph: CanonicalInfrastructureGraph,
        assessment: MigrationAssessment,
        translation: TranslationReport,
    ) -> ReadinessAssessment:
        checklist: dict[str, bool] = {}

        # Check 1: All resources translated
        unsupported = [tr for tr in translation.results if tr.status is SupportStatus.UNSUPPORTED]
        checklist["all_resources_translated"] = len(unsupported) == 0

        # Check 2: No critical blockers
        checklist["no_critical_blockers"] = len(assessment.blockers) == 0

        # Check 3: Risk level acceptable
        checklist["risk_level_acceptable"] = assessment.risk_level.value != "high"

        # Check 4: All resources have owners
        unowned = [r for r in graph.resources.values() if not r.owner]
        checklist["all_resources_owned"] = len(unowned) == 0

        # Check 5: Complexity manageable
        checklist["complexity_manageable"] = assessment.overall_complexity_score <= 70

        # Check 6: Manual resources planned
        manual = [a for a in assessment.resource_assessments if a.strategy is MigrationStrategy.MANUAL]
        checklist["manual_resources_planned"] = len(manual) <= 2

        # Check 7: Migration phases defined
        checklist["phases_defined"] = len(assessment.phases) > 0

        # Compute score
        passed = sum(1 for v in checklist.values() if v)
        total = len(checklist)
        score = int(passed / total * 100) if total > 0 else 0

        if score >= 80:
            readiness = "ready"
        elif score >= 50:
            readiness = "partially_ready"
        else:
            readiness = "not_ready"

        blockers_remaining = sum(1 for v in checklist.values() if not v)

        return ReadinessAssessment(
            overall_readiness=readiness,
            checklist=checklist,
            blockers_remaining=blockers_remaining,
            readiness_score=score,
        )


# ---------------------------------------------------------------------------
# Mermaid Dependency Visualization
# ---------------------------------------------------------------------------


def generate_mermaid_diagram(graph: CanonicalInfrastructureGraph) -> str:
    """Generate a Mermaid flowchart from the canonical dependency graph."""
    lines = ["graph TD"]

    # Define nodes with labels
    for resource in graph.resources.values():
        category = resource.canonical_type.value.split(".")[0]
        icon_map = {
            "network": "🌐", "compute": "🖥️", "storage": "📦",
            "database": "🗄️", "iam": "🔐", "security": "🛡️",
            "dns": "🌍", "messaging": "📨", "monitoring": "📊",
            "cdn": "⚡", "secrets": "🔑",
        }
        icon = icon_map.get(category, "📋")
        safe_id = resource.id.replace(":", "_").replace(".", "_").replace("-", "_")
        label = f"{icon} {resource.name}"
        lines.append(f'    {safe_id}["{label}"]')

    # Define edges
    for resource in graph.resources.values():
        source_id = resource.id.replace(":", "_").replace(".", "_").replace("-", "_")
        for dep_id in resource.depends_on:
            if dep_id in graph.resources:
                target_id = dep_id.replace(":", "_").replace(".", "_").replace("-", "_")
                lines.append(f"    {target_id} --> {source_id}")

    # Style by category
    category_styles: dict[str, list[str]] = {}
    for resource in graph.resources.values():
        category = resource.canonical_type.value.split(".")[0]
        safe_id = resource.id.replace(":", "_").replace(".", "_").replace("-", "_")
        category_styles.setdefault(category, []).append(safe_id)

    color_map = {
        "network": "#4A90D9", "compute": "#7B68EE", "storage": "#F5A623",
        "database": "#D0021B", "iam": "#417505", "security": "#417505",
        "dns": "#4A90D9", "messaging": "#9013FE", "monitoring": "#50E3C2",
    }

    for category, node_ids in category_styles.items():
        color = color_map.get(category, "#888888")
        class_name = f"cls_{category}"
        lines.append(f"    classDef {class_name} fill:{color},stroke:#333,color:#fff")
        lines.append(f"    class {','.join(node_ids)} {class_name}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Version Management
# ---------------------------------------------------------------------------


class PlatformVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    platform_version: str = "0.6.0"
    canonical_schema_version: str = "1.0.0"
    capability_matrix_version: str = "2.0.0"
    python_version_required: str = ">=3.11"
    supported_providers: list[str] = Field(default_factory=lambda: ["aws", "gcp"])
    supported_target_providers: list[str] = Field(default_factory=lambda: ["gcp", "aws"])
    engine_count: int = 18
    canonical_type_count: int = 29
    policy_check_count: int = 11
    parser_count: int = 5


def get_platform_version() -> PlatformVersion:
    return PlatformVersion()
