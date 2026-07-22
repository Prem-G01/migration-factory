"""CIS Benchmark and NIST control mapping rule packs.

These are DATA — JSON-equivalent PolicyDefinition lists that extend the
default policy pack with framework-specific checks. Load them by passing
to PolicyEngine(policies=CIS_POLICIES + NIST_POLICIES + DEFAULT_POLICIES).
"""

from __future__ import annotations

from migration_factory.policy.models import PolicyDefinition, PolicySeverity

CIS_POLICIES: list[PolicyDefinition] = [
    PolicyDefinition(
        check_id="encryption.at_rest",
        name="CIS 2.1.1 — Encryption at rest",
        description="Ensure all storage and database resources have encryption at rest enabled",
        severity=PolicySeverity.CRITICAL,
        category="encryption",
        frameworks=["CIS"],
        remediation="Enable encryption using KMS or provider-managed keys.",
    ),
    PolicyDefinition(
        check_id="access.no_public",
        name="CIS 2.1.2 — No public access",
        description="Ensure S3/GCS buckets and databases are not publicly accessible",
        severity=PolicySeverity.CRITICAL,
        category="access",
        frameworks=["CIS"],
        remediation="Remove public access; use private endpoints.",
    ),
    PolicyDefinition(
        check_id="network.isolation",
        name="CIS 4.1 — VPC network isolation",
        description="Ensure compute and database resources are within a VPC",
        severity=PolicySeverity.HIGH,
        category="network",
        frameworks=["CIS"],
        remediation="Deploy within a VPC with proper subnet configuration.",
    ),
    PolicyDefinition(
        check_id="iam.least_privilege",
        name="CIS 1.16 — Least privilege IAM",
        description="Ensure IAM policies do not use wildcard permissions",
        severity=PolicySeverity.CRITICAL,
        category="iam",
        frameworks=["CIS"],
        remediation="Replace wildcard permissions with specific, scoped permissions.",
    ),
    PolicyDefinition(
        check_id="security.zero_trust",
        name="CIS 4.3 — Restrict default security group",
        description="Ensure no security group allows unrestricted inbound access",
        severity=PolicySeverity.HIGH,
        category="security",
        frameworks=["CIS"],
        remediation="Remove 0.0.0.0/0 rules and implement explicit allow-listing.",
    ),
    PolicyDefinition(
        check_id="tags.required",
        name="CIS 1.20 — Resource tagging",
        description="Ensure all resources have required tags for identification",
        severity=PolicySeverity.MEDIUM,
        category="tags",
        frameworks=["CIS"],
        remediation="Add required tags (Name, Environment, Owner).",
    ),
]


NIST_POLICIES: list[PolicyDefinition] = [
    PolicyDefinition(
        check_id="encryption.at_rest",
        name="NIST SC-28 — Protection of information at rest",
        description="Cryptographic mechanisms prevent unauthorized disclosure of information at rest",
        severity=PolicySeverity.CRITICAL,
        category="encryption",
        frameworks=["NIST"],
        remediation="Enable encryption at rest with customer-managed or provider-managed keys.",
    ),
    PolicyDefinition(
        check_id="access.no_public",
        name="NIST AC-3 — Access enforcement",
        description="Enforce approved authorizations for logical access to resources",
        severity=PolicySeverity.CRITICAL,
        category="access",
        frameworks=["NIST"],
        remediation="Implement access controls; remove public access.",
    ),
    PolicyDefinition(
        check_id="iam.least_privilege",
        name="NIST AC-6 — Least privilege",
        description="Employ the principle of least privilege for system access",
        severity=PolicySeverity.CRITICAL,
        category="iam",
        frameworks=["NIST"],
        remediation="Restrict IAM permissions to minimum required.",
    ),
    PolicyDefinition(
        check_id="network.isolation",
        name="NIST SC-7 — Boundary protection",
        description="Monitor and control communications at external boundaries",
        severity=PolicySeverity.HIGH,
        category="network",
        frameworks=["NIST"],
        remediation="Deploy within VPC with boundary controls.",
    ),
    PolicyDefinition(
        check_id="security.zero_trust",
        name="NIST AC-17 — Remote access",
        description="Authorize, monitor, and control remote access sessions",
        severity=PolicySeverity.HIGH,
        category="security",
        frameworks=["NIST"],
        remediation="Restrict inbound access to authorized sources only.",
    ),
    PolicyDefinition(
        check_id="region.allowed",
        name="NIST PE-18 — Location of system components",
        description="Position system components within the facility to minimize damage",
        severity=PolicySeverity.MEDIUM,
        category="region",
        frameworks=["NIST"],
        remediation="Deploy in approved regions only.",
    ),
]
