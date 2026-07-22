"""Built-in policy checks and the evaluation engine.

Every check is a pure function: (resource, graph, policy, parameters) ->
PolicyFinding. No side effects, no external calls — deterministic and
unit-testable in isolation. The engine dispatches by `check_id` and
collects results into a PolicyReport.
"""

from __future__ import annotations

import json
from typing import Any

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
)
from migration_factory.domain.enums import CanonicalResourceType
from migration_factory.policy.models import (
    PolicyDefinition,
    PolicyFinding,
    PolicyReport,
    PolicySeverity,
    PolicyStatus,
)

logger = get_logger(__name__)


# Using a simpler callable type
CheckCallable = Any


def _finding(
    policy: PolicyDefinition,
    resource: CanonicalResource,
    status: PolicyStatus,
    message: str,
) -> PolicyFinding:
    return PolicyFinding(
        check_id=policy.check_id,
        check_name=policy.name,
        resource_id=resource.id,
        resource_name=resource.name,
        status=status,
        severity=policy.severity,
        category=policy.category,
        message=message,
        remediation=policy.remediation,
        frameworks=list(policy.frameworks),
    )


# ---------------------------------------------------------------------------
# Built-in checks
# ---------------------------------------------------------------------------


def check_naming_prefix(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Validates resource names start with a required prefix."""
    prefix = parameters.get("required_prefix", "")
    if not prefix:
        return _finding(policy, resource, PolicyStatus.SKIP, "No prefix configured")
    if resource.name.startswith(prefix):
        return _finding(policy, resource, PolicyStatus.PASS, f"Name starts with '{prefix}'")
    return _finding(
        policy, resource, PolicyStatus.FAIL,
        f"Name '{resource.name}' does not start with required prefix '{prefix}'",
    )


def check_required_tags(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Validates required tags/labels are present."""
    required: list[str] = parameters.get("required_tags", [])
    if not required:
        return _finding(policy, resource, PolicyStatus.SKIP, "No required tags configured")
    missing = [t for t in required if t not in resource.tags]
    if not missing:
        return _finding(policy, resource, PolicyStatus.PASS, "All required tags present")
    return _finding(
        policy, resource, PolicyStatus.FAIL,
        f"Missing required tags: {', '.join(missing)}",
    )


def check_encryption_at_rest(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Checks for encryption configuration on storage/database resources."""
    encryptable_types = {
        CanonicalResourceType.STORAGE_OBJECT_BUCKET,
        CanonicalResourceType.DATABASE_INSTANCE,
    }
    if resource.canonical_type not in encryptable_types:
        return _finding(policy, resource, PolicyStatus.SKIP, "Not an encryptable resource type")

    attrs = resource.native_attributes
    # Check common encryption attribute patterns
    encrypted = (
        attrs.get("server_side_encryption_configuration")
        or attrs.get("kms_key_id")
        or attrs.get("storage_encrypted")
        or attrs.get("encryption_configuration")
    )
    if encrypted:
        return _finding(policy, resource, PolicyStatus.PASS, "Encryption at rest configured")
    return _finding(
        policy, resource, PolicyStatus.FAIL,
        "No encryption at rest configuration detected",
    )


def check_no_public_access(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Checks for public access indicators on resources."""
    attrs = resource.native_attributes

    public_indicators = [
        attrs.get("publicly_accessible"),
        attrs.get("map_public_ip_on_launch"),
    ]

    # Check for 0.0.0.0/0 in firewall/SG rules
    if resource.canonical_type is CanonicalResourceType.NETWORK_FIREWALL_RULE:
        ingress = attrs.get("ingress", [])
        if isinstance(ingress, list):
            for rule in ingress:
                cidr_blocks = rule.get("cidr_blocks", []) if isinstance(rule, dict) else []
                if "0.0.0.0/0" in cidr_blocks:
                    return _finding(
                        policy, resource, PolicyStatus.FAIL,
                        "Firewall rule allows ingress from 0.0.0.0/0 (all IPs)",
                    )

    if any(v is True for v in public_indicators):
        return _finding(policy, resource, PolicyStatus.FAIL, "Resource has public access enabled")

    return _finding(policy, resource, PolicyStatus.PASS, "No public access detected")


def check_allowed_regions(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Validates resources are in allowed regions only."""
    allowed: list[str] = parameters.get("allowed_regions", [])
    if not allowed:
        return _finding(policy, resource, PolicyStatus.SKIP, "No allowed regions configured")
    if resource.region is None or resource.region == "global":
        return _finding(policy, resource, PolicyStatus.PASS, "Global resource, region N/A")
    if resource.region in allowed:
        return _finding(policy, resource, PolicyStatus.PASS, f"Region '{resource.region}' is allowed")
    return _finding(
        policy, resource, PolicyStatus.FAIL,
        f"Region '{resource.region}' is not in allowed list: {', '.join(allowed)}",
    )


def check_network_isolation(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Checks compute/database resources are in a VPC (not default/public)."""
    vpc_types = {
        CanonicalResourceType.COMPUTE_INSTANCE,
        CanonicalResourceType.DATABASE_INSTANCE,
    }
    if resource.canonical_type not in vpc_types:
        return _finding(policy, resource, PolicyStatus.SKIP, "Not a VPC-attached resource type")

    attrs = resource.native_attributes
    vpc_id = attrs.get("vpc_id") or attrs.get("vpc_security_group_ids")
    subnet_id = attrs.get("subnet_id")

    if not vpc_id and not subnet_id:
        return _finding(policy, resource, PolicyStatus.FAIL, "No VPC/subnet association detected")
    return _finding(policy, resource, PolicyStatus.PASS, "Resource is VPC-attached")


# ---------------------------------------------------------------------------
# Check registry mapping
# ---------------------------------------------------------------------------

CHECK_IMPLEMENTATIONS: dict[str, Any] = {
    "naming.resource_prefix": check_naming_prefix,
    "tags.required": check_required_tags,
    "encryption.at_rest": check_encryption_at_rest,
    "access.no_public": check_no_public_access,
    "region.allowed": check_allowed_regions,
    "network.isolation": check_network_isolation,
}


def check_tag_values(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Validates tag values match allowed patterns."""
    allowed_values: dict[str, list[str]] = parameters.get("allowed_tag_values", {})
    if not allowed_values:
        return _finding(policy, resource, PolicyStatus.SKIP, "No tag value constraints configured")
    violations = []
    for tag_key, allowed in allowed_values.items():
        if tag_key in resource.tags and resource.tags[tag_key] not in allowed:
            violations.append(f"{tag_key}={resource.tags[tag_key]} (allowed: {', '.join(allowed)})")
    if violations:
        return _finding(policy, resource, PolicyStatus.FAIL, f"Invalid tag values: {'; '.join(violations)}")
    return _finding(policy, resource, PolicyStatus.PASS, "All tag values are valid")


def check_label_convention(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Validates labels follow GCP conventions (lowercase, hyphens, max 63 chars)."""
    violations = []
    for key, value in resource.tags.items():
        if key != key.lower():
            violations.append(f"key '{key}' must be lowercase")
        if len(key) > 63 or len(value) > 63:
            violations.append(f"key/value '{key}' exceeds 63 characters")
        if not all(c.isalnum() or c in "-_" for c in key):
            violations.append(f"key '{key}' contains invalid characters")
    if violations:
        return _finding(policy, resource, PolicyStatus.FAIL, f"Label violations: {'; '.join(violations[:3])}")
    return _finding(policy, resource, PolicyStatus.PASS, "Labels follow conventions")


def check_org_hierarchy(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Validates resource has required org metadata (owner, cost_center, environment)."""
    required_fields = parameters.get("required_org_fields", ["owner", "environment"])
    missing = []
    for field_name in required_fields:
        value = getattr(resource, field_name, None)
        if not value and field_name not in resource.tags:
            missing.append(field_name)
    if missing:
        return _finding(policy, resource, PolicyStatus.FAIL, f"Missing org metadata: {', '.join(missing)}")
    return _finding(policy, resource, PolicyStatus.PASS, "Organization metadata complete")


def check_least_privilege(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Checks IAM resources for overly broad permissions."""
    if resource.canonical_type not in {CanonicalResourceType.IAM_ROLE, CanonicalResourceType.IAM_POLICY}:
        return _finding(policy, resource, PolicyStatus.SKIP, "Not an IAM resource")
    attrs = resource.native_attributes
    policy_str = json.dumps(attrs)
    violations = []
    if '"*"' in policy_str and '"Action"' in policy_str:
        violations.append("Wildcard action ('*') detected")
    if '"Resource": "*"' in policy_str or '"resource": "*"' in policy_str:
        violations.append("Wildcard resource ('*') detected")
    if "AdministratorAccess" in policy_str:
        violations.append("AdministratorAccess policy attached")
    if violations:
        return _finding(policy, resource, PolicyStatus.FAIL, f"Least privilege violations: {'; '.join(violations)}")
    return _finding(policy, resource, PolicyStatus.PASS, "No obvious over-privilege detected")


def check_zero_trust(
    resource: CanonicalResource,
    graph: CanonicalInfrastructureGraph,
    policy: PolicyDefinition,
    parameters: dict[str, Any],
) -> PolicyFinding:
    """Zero trust validation: no implicit trust, explicit auth required."""
    if resource.canonical_type is CanonicalResourceType.NETWORK_FIREWALL_RULE:
        attrs = resource.native_attributes
        ingress = attrs.get("ingress", [])
        if isinstance(ingress, list):
            for rule in ingress:
                if isinstance(rule, dict):
                    cidr_blocks = rule.get("cidr_blocks", [])
                    if any(cidr in ("0.0.0.0/0", "::/0") for cidr in cidr_blocks if isinstance(cidr, str)):
                        return _finding(policy, resource, PolicyStatus.FAIL, "Zero trust violation: unrestricted inbound access")
    return _finding(policy, resource, PolicyStatus.PASS, "No zero trust violations detected")


# Register new checks
CHECK_IMPLEMENTATIONS["tags.values"] = check_tag_values
CHECK_IMPLEMENTATIONS["labels.convention"] = check_label_convention
CHECK_IMPLEMENTATIONS["org.hierarchy"] = check_org_hierarchy
CHECK_IMPLEMENTATIONS["iam.least_privilege"] = check_least_privilege
CHECK_IMPLEMENTATIONS["security.zero_trust"] = check_zero_trust


# ---------------------------------------------------------------------------
# Default policy pack
# ---------------------------------------------------------------------------

DEFAULT_POLICIES: list[PolicyDefinition] = [
    PolicyDefinition(
        check_id="naming.resource_prefix",
        name="Resource naming prefix",
        description="Ensure all resources follow the organization naming convention",
        severity=PolicySeverity.MEDIUM,
        category="naming",
        frameworks=[],
        remediation="Rename resources to start with the required prefix.",
    ),
    PolicyDefinition(
        check_id="tags.required",
        name="Required tags",
        description="Ensure all resources have mandatory tags for cost allocation and ownership",
        severity=PolicySeverity.HIGH,
        category="tags",
        frameworks=["SOC2", "ISO27001"],
        remediation="Add the missing tags to the resource.",
    ),
    PolicyDefinition(
        check_id="encryption.at_rest",
        name="Encryption at rest",
        description="Ensure storage and database resources have encryption enabled",
        severity=PolicySeverity.CRITICAL,
        category="encryption",
        frameworks=["CIS", "NIST", "SOC2", "PCI_DSS", "ISO27001", "HIPAA"],
        remediation="Enable encryption at rest using KMS or provider-managed keys.",
    ),
    PolicyDefinition(
        check_id="access.no_public",
        name="No public access",
        description="Ensure resources are not publicly accessible",
        severity=PolicySeverity.CRITICAL,
        category="access",
        frameworks=["CIS", "NIST", "SOC2", "PCI_DSS", "HIPAA"],
        remediation="Remove public access and use private endpoints or VPN.",
    ),
    PolicyDefinition(
        check_id="region.allowed",
        name="Allowed regions",
        description="Ensure resources are deployed only in approved regions",
        severity=PolicySeverity.HIGH,
        category="region",
        frameworks=["SOC2", "ISO27001"],
        remediation="Migrate the resource to an approved region.",
    ),
    PolicyDefinition(
        check_id="network.isolation",
        name="Network isolation",
        description="Ensure compute and database resources are within a VPC",
        severity=PolicySeverity.HIGH,
        category="network",
        frameworks=["CIS", "NIST", "PCI_DSS"],
        remediation="Deploy the resource within a VPC with proper subnet configuration.",
    ),
    PolicyDefinition(
        check_id="tags.values",
        name="Tag value validation",
        description="Ensure tag values match allowed patterns (e.g., Environment must be dev/staging/prod)",
        severity=PolicySeverity.MEDIUM,
        category="tags",
        frameworks=["SOC2"],
        remediation="Update tag values to match the allowed set.",
    ),
    PolicyDefinition(
        check_id="labels.convention",
        name="Label naming conventions",
        description="Ensure labels follow GCP conventions (lowercase, hyphens, max 63 chars)",
        severity=PolicySeverity.LOW,
        category="labels",
        frameworks=[],
        remediation="Rename labels to follow lowercase-with-hyphens convention, max 63 characters.",
    ),
    PolicyDefinition(
        check_id="org.hierarchy",
        name="Organization metadata",
        description="Ensure resources have required organizational metadata (owner, environment)",
        severity=PolicySeverity.MEDIUM,
        category="organization",
        frameworks=["SOC2", "ISO27001"],
        remediation="Add owner and environment metadata via tags or the discovery enrichment engine.",
    ),
    PolicyDefinition(
        check_id="iam.least_privilege",
        name="Least privilege",
        description="Ensure IAM resources do not have overly broad permissions",
        severity=PolicySeverity.CRITICAL,
        category="iam",
        frameworks=["CIS", "NIST", "SOC2", "PCI_DSS", "ISO27001"],
        remediation="Replace wildcard permissions with specific, scoped permissions.",
    ),
    PolicyDefinition(
        check_id="security.zero_trust",
        name="Zero trust validation",
        description="Ensure no implicit trust — all access must be explicitly authorized",
        severity=PolicySeverity.HIGH,
        category="security",
        frameworks=["NIST", "CIS"],
        remediation="Remove unrestricted inbound rules and implement explicit allow-listing.",
    ),
]


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """Evaluates a set of policy definitions against a canonical graph.

    Thread-safe, stateless, deterministic.
    """

    def __init__(
        self,
        policies: list[PolicyDefinition] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self.policies = policies or DEFAULT_POLICIES
        self.parameters = parameters or {}

    def evaluate(self, graph: CanonicalInfrastructureGraph) -> PolicyReport:
        findings: list[PolicyFinding] = []

        for resource in graph.resources.values():
            for policy in self.policies:
                if not policy.enabled:
                    continue
                check_fn = CHECK_IMPLEMENTATIONS.get(policy.check_id)
                if check_fn is None:
                    findings.append(
                        PolicyFinding(
                            check_id=policy.check_id,
                            check_name=policy.name,
                            resource_id=resource.id,
                            resource_name=resource.name,
                            status=PolicyStatus.SKIP,
                            severity=policy.severity,
                            category=policy.category,
                            message=f"No implementation registered for check {policy.check_id!r}",
                            frameworks=list(policy.frameworks),
                        )
                    )
                    continue

                try:
                    finding = check_fn(resource, graph, policy, self.parameters)
                    findings.append(finding)
                except Exception as exc:
                    findings.append(
                        PolicyFinding(
                            check_id=policy.check_id,
                            check_name=policy.name,
                            resource_id=resource.id,
                            resource_name=resource.name,
                            status=PolicyStatus.SKIP,
                            severity=policy.severity,
                            category=policy.category,
                            message=f"Check raised exception: {exc}",
                            frameworks=list(policy.frameworks),
                        )
                    )

        logger.info(
            "policy_evaluation_completed",
            resource_count=len(graph.resources),
            policy_count=len(self.policies),
            finding_count=len(findings),
            **{f"status_{k}": v for k, v in PolicyReport(findings=findings).summary.items()},
        )
        return PolicyReport(findings=findings)
