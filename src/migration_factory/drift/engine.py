"""Drift Detection and State Reconciliation Engine.

Compares canonical graph (desired state) against actual cloud state
(discovered) or Terraform state to detect drift, missing resources,
orphan resources, and configuration changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph

logger = get_logger(__name__)


class DriftType(StrEnum):
    MISSING = "missing"  # in desired, not in actual
    ORPHAN = "orphan"  # in actual, not in desired
    MODIFIED = "modified"  # exists in both, attributes differ
    MATCH = "match"  # identical


class DriftFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: str
    resource_name: str
    drift_type: DriftType
    message: str
    desired_value: str = ""
    actual_value: str = ""


class DriftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_resources_checked: int = 0
    missing_count: int = 0
    orphan_count: int = 0
    modified_count: int = 0
    match_count: int = 0
    findings: list[DriftFinding] = Field(default_factory=list)
    drift_detected: bool = False
    recommendations: list[str] = Field(default_factory=list)


class ReconciliationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: str
    action: str  # import, update, delete, ignore
    description: str
    risk: str = "low"


class ReconciliationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[ReconciliationAction] = Field(default_factory=list)
    import_commands: list[str] = Field(default_factory=list)
    total_actions: int = 0


@dataclass(slots=True)
class DriftDetectionEngine:
    """Compares desired state (canonical graph) against actual state."""

    def detect(
        self,
        desired: CanonicalInfrastructureGraph,
        actual: CanonicalInfrastructureGraph,
    ) -> DriftReport:
        findings: list[DriftFinding] = []
        desired_ids = set(desired.resources.keys())
        actual_ids = set(actual.resources.keys())

        # Missing: in desired but not actual
        for rid in sorted(desired_ids - actual_ids):
            r = desired.resources[rid]
            findings.append(DriftFinding(
                resource_id=rid, resource_name=r.name, drift_type=DriftType.MISSING,
                message=f"Resource exists in desired state but not in actual cloud: {r.canonical_type.value}",
            ))

        # Orphan: in actual but not desired
        for rid in sorted(actual_ids - desired_ids):
            r = actual.resources[rid]
            findings.append(DriftFinding(
                resource_id=rid, resource_name=r.name, drift_type=DriftType.ORPHAN,
                message=f"Resource exists in cloud but not in desired state: {r.canonical_type.value}",
            ))

        # Modified: in both, check for differences
        for rid in sorted(desired_ids & actual_ids):
            d = desired.resources[rid]
            a = actual.resources[rid]

            diffs: list[str] = []
            if d.canonical_type != a.canonical_type:
                diffs.append(f"type: {d.canonical_type.value} vs {a.canonical_type.value}")
            if d.region != a.region:
                diffs.append(f"region: {d.region} vs {a.region}")
            if d.tags != a.tags:
                diffs.append("tags differ")

            if diffs:
                findings.append(DriftFinding(
                    resource_id=rid, resource_name=d.name, drift_type=DriftType.MODIFIED,
                    message=f"Configuration drift: {'; '.join(diffs)}",
                    desired_value=str(d.tags), actual_value=str(a.tags),
                ))
            else:
                findings.append(DriftFinding(
                    resource_id=rid, resource_name=d.name, drift_type=DriftType.MATCH,
                    message="No drift detected",
                ))

        missing = sum(1 for f in findings if f.drift_type is DriftType.MISSING)
        orphan = sum(1 for f in findings if f.drift_type is DriftType.ORPHAN)
        modified = sum(1 for f in findings if f.drift_type is DriftType.MODIFIED)
        match = sum(1 for f in findings if f.drift_type is DriftType.MATCH)

        recs: list[str] = []
        if missing > 0:
            recs.append(f"{missing} resources need to be created (terraform apply)")
        if orphan > 0:
            recs.append(f"{orphan} orphan resources should be imported or removed")
        if modified > 0:
            recs.append(f"{modified} resources have configuration drift (terraform apply to reconcile)")

        report = DriftReport(
            total_resources_checked=len(desired_ids | actual_ids),
            missing_count=missing, orphan_count=orphan, modified_count=modified, match_count=match,
            findings=findings, drift_detected=(missing + orphan + modified) > 0, recommendations=recs,
        )

        logger.info("drift_detection_completed", missing=missing, orphan=orphan, modified=modified, match=match)
        return report


@dataclass(slots=True)
class StateReconciliationEngine:
    """Generates a reconciliation plan from drift findings."""

    def reconcile(self, drift_report: DriftReport) -> ReconciliationPlan:
        actions: list[ReconciliationAction] = []
        import_commands: list[str] = []

        for finding in drift_report.findings:
            if finding.drift_type is DriftType.MISSING:
                actions.append(ReconciliationAction(
                    resource_id=finding.resource_id, action="create",
                    description=f"Create {finding.resource_name} via terraform apply",
                    risk="medium",
                ))
            elif finding.drift_type is DriftType.ORPHAN:
                actions.append(ReconciliationAction(
                    resource_id=finding.resource_id, action="import",
                    description=f"Import {finding.resource_name} into Terraform state",
                    risk="low",
                ))
                import_commands.append(f"terraform import <resource_address> {finding.resource_id}")
            elif finding.drift_type is DriftType.MODIFIED:
                actions.append(ReconciliationAction(
                    resource_id=finding.resource_id, action="update",
                    description=f"Reconcile drift on {finding.resource_name} via terraform apply",
                    risk="medium",
                ))

        plan = ReconciliationPlan(actions=actions, import_commands=import_commands, total_actions=len(actions))
        logger.info("reconciliation_plan_generated", total_actions=len(actions))
        return plan
