"""Security Engine.

Runs security-specific analysis against the canonical graph: IAM review,
secret detection, encryption validation, firewall analysis, public exposure
detection, network security, and an overall security risk score.

Built ON TOP of the Policy Engine — security checks are just policies tagged
to security frameworks, plus domain-specific analysis (IAM decomposition,
secret scanning) that goes beyond single-resource predicate evaluation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
)
from migration_factory.domain.enums import CanonicalResourceType
from migration_factory.policy.engine import PolicyEngine
from migration_factory.policy.models import PolicyReport, PolicySeverity

logger = get_logger(__name__)

# Common secret patterns (compiled once)
_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|api_key|apikey|access_key|token)"),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key ID
    re.compile(r"(?i)-----BEGIN\s*(RSA|DSA|EC|OPENSSH)\s*PRIVATE\s*KEY-----"),
]


class SecurityRiskLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IAMFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    resource_name: str
    finding_type: str
    message: str
    severity: PolicySeverity
    remediation: str


class SecretFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    resource_name: str
    attribute_path: str
    pattern_matched: str
    severity: PolicySeverity = PolicySeverity.CRITICAL
    remediation: str = "Move secrets to a secrets manager and reference by ARN/name."


class FirewallFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    resource_name: str
    finding_type: str
    message: str
    severity: PolicySeverity


class SecurityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    security_score: int = Field(..., ge=0, le=100, description="Higher = more secure")
    risk_level: SecurityRiskLevel
    policy_report: PolicyReport
    iam_findings: list[IAMFinding] = Field(default_factory=list)
    secret_findings: list[SecretFinding] = Field(default_factory=list)
    firewall_findings: list[FirewallFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


@dataclass(slots=True)
class SecurityEngine:
    policy_engine: PolicyEngine = field(default_factory=PolicyEngine)

    def analyze(self, graph: CanonicalInfrastructureGraph) -> SecurityReport:
        # Run policy checks (encryption, public access, network isolation)
        policy_report = self.policy_engine.evaluate(graph)

        # Domain-specific analysis
        iam_findings = self._analyze_iam(graph)
        secret_findings = self._scan_secrets(graph)
        firewall_findings = self._analyze_firewalls(graph)

        # Compute score
        all_critical = (
            sum(1 for f in policy_report.failed if f.severity is PolicySeverity.CRITICAL)
            + sum(1 for f in iam_findings if f.severity is PolicySeverity.CRITICAL)
            + len(secret_findings)
            + sum(1 for f in firewall_findings if f.severity is PolicySeverity.CRITICAL)
        )
        all_high = (
            sum(1 for f in policy_report.failed if f.severity is PolicySeverity.HIGH)
            + sum(1 for f in iam_findings if f.severity is PolicySeverity.HIGH)
            + sum(1 for f in firewall_findings if f.severity is PolicySeverity.HIGH)
        )

        raw_score = 100 - (all_critical * 15) - (all_high * 8)
        security_score = max(0, min(100, raw_score))

        if all_critical > 0:
            risk_level = SecurityRiskLevel.CRITICAL
        elif all_high > 2:
            risk_level = SecurityRiskLevel.HIGH
        elif all_high > 0:
            risk_level = SecurityRiskLevel.MEDIUM
        else:
            risk_level = SecurityRiskLevel.LOW

        report = SecurityReport(
            security_score=security_score,
            risk_level=risk_level,
            policy_report=policy_report,
            iam_findings=iam_findings,
            secret_findings=secret_findings,
            firewall_findings=firewall_findings,
            summary={
                "critical_findings": all_critical,
                "high_findings": all_high,
                "iam_findings": len(iam_findings),
                "secrets_detected": len(secret_findings),
                "firewall_findings": len(firewall_findings),
            },
        )

        logger.info(
            "security_analysis_completed",
            security_score=security_score,
            risk_level=risk_level.value,
            critical=all_critical,
            high=all_high,
        )
        return report

    @staticmethod
    def _analyze_iam(graph: CanonicalInfrastructureGraph) -> list[IAMFinding]:
        findings: list[IAMFinding] = []
        for resource in graph.resources.values():
            if resource.canonical_type is not CanonicalResourceType.IAM_ROLE:
                continue

            attrs = resource.native_attributes

            # Check for wildcard policies (overly permissive)
            assume_role_policy = str(attrs.get("assume_role_policy", ""))
            if '"*"' in assume_role_policy or "'*'" in assume_role_policy:
                findings.append(IAMFinding(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    finding_type="overly_permissive_trust",
                    message="Trust policy contains wildcard principal ('*') — any AWS account can assume this role",
                    severity=PolicySeverity.CRITICAL,
                    remediation="Restrict the trust policy principal to specific AWS accounts or services.",
                ))

            # Check for admin-level managed policies
            managed_policies = attrs.get("managed_policy_arns", [])
            if isinstance(managed_policies, list):
                for arn in managed_policies:
                    if "AdministratorAccess" in str(arn):
                        findings.append(IAMFinding(
                            resource_id=resource.id,
                            resource_name=resource.name,
                            finding_type="admin_access",
                            message=f"Role has AdministratorAccess policy attached: {arn}",
                            severity=PolicySeverity.CRITICAL,
                            remediation="Replace AdministratorAccess with least-privilege custom policies.",
                        ))

            # Check for inline policies (should be managed)
            if attrs.get("inline_policy"):
                findings.append(IAMFinding(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    finding_type="inline_policy",
                    message="Role uses inline policies instead of managed policies",
                    severity=PolicySeverity.MEDIUM,
                    remediation="Convert inline policies to managed policies for reusability and auditability.",
                ))

        return findings

    @staticmethod
    def _scan_secrets(graph: CanonicalInfrastructureGraph) -> list[SecretFinding]:
        findings: list[SecretFinding] = []

        def _scan_dict(attrs: dict[str, object], path: str, resource: CanonicalResource) -> None:
            for key, value in attrs.items():
                current_path = f"{path}.{key}"
                str_value = str(value) if value is not None else ""
                for pattern in _SECRET_PATTERNS:
                    if pattern.search(str_value) and len(str_value) > 5:
                        findings.append(SecretFinding(
                            resource_id=resource.id,
                            resource_name=resource.name,
                            attribute_path=current_path,
                            pattern_matched=pattern.pattern,
                        ))
                        break
                if isinstance(value, dict):
                    _scan_dict(value, current_path, resource)

        for resource in graph.resources.values():
            _scan_dict(resource.native_attributes, "attributes", resource)

        return findings

    @staticmethod
    def _analyze_firewalls(graph: CanonicalInfrastructureGraph) -> list[FirewallFinding]:
        findings: list[FirewallFinding] = []

        for resource in graph.resources.values():
            if resource.canonical_type is not CanonicalResourceType.NETWORK_FIREWALL_RULE:
                continue

            attrs = resource.native_attributes
            ingress = attrs.get("ingress", [])

            if isinstance(ingress, list):
                for rule in ingress:
                    if not isinstance(rule, dict):
                        continue
                    cidr_blocks = rule.get("cidr_blocks", [])
                    from_port = rule.get("from_port", 0)
                    to_port = rule.get("to_port", 65535)

                    if "0.0.0.0/0" in cidr_blocks:
                        if from_port == 0 and to_port == 65535:
                            findings.append(FirewallFinding(
                                resource_id=resource.id,
                                resource_name=resource.name,
                                finding_type="open_all_ports",
                                message="Security group allows ALL traffic from 0.0.0.0/0",
                                severity=PolicySeverity.CRITICAL,
                            ))
                        elif from_port == 22 or to_port == 22:
                            findings.append(FirewallFinding(
                                resource_id=resource.id,
                                resource_name=resource.name,
                                finding_type="ssh_open_to_world",
                                message="SSH (port 22) is open to 0.0.0.0/0",
                                severity=PolicySeverity.HIGH,
                            ))
                        elif from_port == 3389 or to_port == 3389:
                            findings.append(FirewallFinding(
                                resource_id=resource.id,
                                resource_name=resource.name,
                                finding_type="rdp_open_to_world",
                                message="RDP (port 3389) is open to 0.0.0.0/0",
                                severity=PolicySeverity.HIGH,
                            ))

        return findings
