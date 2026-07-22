"""Root Cause Analysis Engine.

Provides structured RCA for infrastructure failures, migration issues,
policy violations, and dependency problems. Every finding is actionable:
a problem statement, root cause, contributing factors, and remediation steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.drift.engine import DriftReport, DriftType
from migration_factory.policy.models import PolicyReport
from migration_factory.security.engine import SecurityReport

logger = get_logger(__name__)


class RCASeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RCAFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: str
    title: str
    severity: RCASeverity
    problem_statement: str
    root_cause: str
    contributing_factors: list[str] = Field(default_factory=list)
    remediation_steps: list[str] = Field(default_factory=list)
    affected_resources: list[str] = Field(default_factory=list)


class RCAReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_findings: int = 0
    critical_count: int = 0
    findings: list[RCAFinding] = Field(default_factory=list)
    summary: str = ""


@dataclass(slots=True)
class RootCauseAnalyzer:
    """Generates structured root cause analysis from engine outputs."""

    def analyze(
        self,
        graph: CanonicalInfrastructureGraph | None = None,
        policy_report: PolicyReport | None = None,
        security_report: SecurityReport | None = None,
        drift_report: DriftReport | None = None,
    ) -> RCAReport:
        findings: list[RCAFinding] = []

        if policy_report:
            findings.extend(self._analyze_policy_failures(policy_report))
        if security_report:
            findings.extend(self._analyze_security_issues(security_report))
        if drift_report:
            findings.extend(self._analyze_drift(drift_report))
        if graph:
            findings.extend(self._analyze_graph_issues(graph))

        critical = sum(1 for f in findings if f.severity is RCASeverity.CRITICAL)
        summary = f"{len(findings)} root cause findings: {critical} critical."
        if not findings:
            summary = "No root cause findings detected — infrastructure is healthy."

        report = RCAReport(
            total_findings=len(findings),
            critical_count=critical,
            findings=findings,
            summary=summary,
        )

        logger.info("rca_completed", findings=len(findings), critical=critical)
        return report

    @staticmethod
    def _analyze_policy_failures(policy_report: PolicyReport) -> list[RCAFinding]:
        findings: list[RCAFinding] = []
        failures = policy_report.failed

        # Group failures by check_id
        by_check: dict[str, list[str]] = {}
        for f in failures:
            by_check.setdefault(f.check_id, []).append(f.resource_id)

        severity_map = {"critical": RCASeverity.CRITICAL, "high": RCASeverity.HIGH, "medium": RCASeverity.MEDIUM, "low": RCASeverity.LOW}

        for check_id, resource_ids in by_check.items():
            # Get a representative finding for context
            rep = next(f for f in failures if f.check_id == check_id)
            sev = severity_map.get(rep.severity.value, RCASeverity.MEDIUM)

            findings.append(RCAFinding(
                finding_id=f"rca_policy_{check_id}",
                title=f"Policy violation: {rep.check_name}",
                severity=sev,
                problem_statement=f"{len(resource_ids)} resources violate policy '{rep.check_name}'",
                root_cause=f"Resources were provisioned without enforcing the '{check_id}' policy control",
                contributing_factors=[
                    "Missing infrastructure governance enforcement at provisioning time",
                    "No automated policy checks in the CI/CD pipeline",
                    f"Policy '{rep.check_name}' may not have been defined when resources were created",
                ],
                remediation_steps=[
                    rep.remediation or f"Apply '{check_id}' policy to all listed resources",
                    "Add policy check to provisioning pipeline to prevent recurrence",
                    "Review and update baseline infrastructure standards",
                ],
                affected_resources=resource_ids,
            ))

        return findings

    @staticmethod
    def _analyze_security_issues(security_report: SecurityReport) -> list[RCAFinding]:
        findings: list[RCAFinding] = []

        if security_report.secret_findings:
            findings.append(RCAFinding(
                finding_id="rca_secrets_in_state",
                title="Secrets detected in infrastructure attributes",
                severity=RCASeverity.CRITICAL,
                problem_statement=f"{len(security_report.secret_findings)} resources contain potential secrets in their attributes",
                root_cause="Secrets were embedded directly in resource attributes instead of a secrets manager",
                contributing_factors=[
                    "No secrets scanning gate in the CI/CD pipeline",
                    "Developer convenience prioritized over security",
                    "Secrets manager integration not implemented at provisioning time",
                ],
                remediation_steps=[
                    "Immediately rotate all detected credentials",
                    "Move secrets to AWS Secrets Manager / GCP Secret Manager",
                    "Reference secrets by ARN/name instead of value in Terraform",
                    "Add pre-commit hooks to block secret commits",
                ],
                affected_resources=[f.resource_id for f in security_report.secret_findings],
            ))

        for iam_f in security_report.iam_findings:
            if iam_f.finding_type == "admin_access":
                findings.append(RCAFinding(
                    finding_id=f"rca_iam_admin_{iam_f.resource_id}",
                    title="IAM role has AdministratorAccess",
                    severity=RCASeverity.CRITICAL,
                    problem_statement=f"Role '{iam_f.resource_name}' has AdministratorAccess policy",
                    root_cause="The role was provisioned with a broad managed policy instead of least-privilege custom permissions",
                    contributing_factors=["Time pressure favored convenience over security", "No IAM review process"],
                    remediation_steps=[
                        "Identify the minimum permissions this role actually uses",
                        "Create a custom IAM policy with only those permissions",
                        "Remove AdministratorAccess and attach the custom policy",
                        "Implement IAM Access Analyzer to detect unused permissions",
                    ],
                    affected_resources=[iam_f.resource_id],
                ))

        return findings

    @staticmethod
    def _analyze_drift(drift_report: DriftReport) -> list[RCAFinding]:
        findings: list[RCAFinding] = []

        missing = [f for f in drift_report.findings if f.drift_type is DriftType.MISSING]
        if missing:
            findings.append(RCAFinding(
                finding_id="rca_drift_missing_resources",
                title="Infrastructure resources missing from actual cloud",
                severity=RCASeverity.HIGH,
                problem_statement=f"{len(missing)} resources exist in desired state but not in actual cloud",
                root_cause="Resources were defined in Terraform but never applied, or were manually deleted outside Terraform",
                contributing_factors=[
                    "Manual changes to cloud infrastructure bypassed Terraform",
                    "Failed terraform apply left partial state",
                    "Resource was removed from state but not from cloud or vice versa",
                ],
                remediation_steps=[
                    "Run terraform plan to confirm the gap",
                    "Run terraform apply to create missing resources, OR",
                    "If intentionally deleted, remove from Terraform configuration",
                ],
                affected_resources=[f.resource_id for f in missing],
            ))

        orphans = [f for f in drift_report.findings if f.drift_type is DriftType.ORPHAN]
        if orphans:
            findings.append(RCAFinding(
                finding_id="rca_drift_orphan_resources",
                title="Orphan resources exist in cloud but not in Terraform state",
                severity=RCASeverity.MEDIUM,
                problem_statement=f"{len(orphans)} resources in actual cloud have no corresponding Terraform state",
                root_cause="Resources were created manually or by another tool outside Terraform",
                contributing_factors=[
                    "Manual cloud console operations",
                    "Another IaC tool managing overlapping resources",
                    "Terraform import never run after manual creation",
                ],
                remediation_steps=[
                    "Run terraform import for each orphan resource",
                    "Add the resource definition to your Terraform configuration",
                    "Enforce policy: all resources must be created via Terraform",
                ],
                affected_resources=[f.resource_id for f in orphans],
            ))

        return findings

    @staticmethod
    def _analyze_graph_issues(graph: CanonicalInfrastructureGraph) -> list[RCAFinding]:
        findings: list[RCAFinding] = []

        dangling = graph.validate_references()
        if dangling:
            findings.append(RCAFinding(
                finding_id="rca_dangling_dependencies",
                title="Resources reference non-existent dependencies",
                severity=RCASeverity.MEDIUM,
                problem_statement=f"{len(dangling)} dependency references point to resources not in scope",
                root_cause="Migration scope was defined without including all dependency resources",
                contributing_factors=[
                    "Partial migration scope (only migrating some resources)",
                    "Dependency analysis was not run before scoping",
                    "Resources in different Terraform workspaces",
                ],
                remediation_steps=[
                    "Expand migration scope to include all dependency resources, OR",
                    "Use data sources to reference existing resources in the target cloud",
                    "Update depends_on to reference the target-cloud equivalent",
                ],
                affected_resources=dangling,
            ))

        return findings
