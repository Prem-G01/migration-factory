"""Validation Engine.

Validates canonical resources and the graph before Terraform generation.
Every validation check produces a structured finding; the engine never
raises on a validation failure (validation is advisory, generation decides
whether to proceed). This matches the platform philosophy: surface
findings, don't block unless policy says to.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
)
from migration_factory.domain.enums import CanonicalResourceType

logger = get_logger(__name__)


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check: str
    resource_id: str
    resource_name: str
    severity: ValidationSeverity
    message: str
    remediation: str = ""


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[ValidationFinding] = Field(default_factory=list)

    @property
    def errors(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.severity is ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.severity is ValidationSeverity.WARNING]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in ValidationSeverity}
        for f in self.findings:
            counts[f.severity.value] += 1
        return counts


# Naming patterns
_VALID_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9\-_]{0,62}$")

# Known valid regions
_AWS_REGIONS = {
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1",
    "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2", "ap-south-1",
    "sa-east-1", "ca-central-1", "me-south-1", "af-south-1", "global",
}
_GCP_REGIONS = {
    "us-central1", "us-east1", "us-east4", "us-west1", "us-west2", "us-west4",
    "europe-west1", "europe-west2", "europe-west3", "europe-west4", "europe-north1",
    "asia-east1", "asia-east2", "asia-southeast1", "asia-northeast1", "asia-south1",
    "southamerica-east1", "australia-southeast1", "global",
}


@dataclass(slots=True)
class ValidationEngine:

    def validate(self, graph: CanonicalInfrastructureGraph) -> ValidationReport:
        findings: list[ValidationFinding] = []

        for resource in graph.resources.values():
            findings.extend(self._validate_naming(resource))
            findings.extend(self._validate_cidr(resource))
            findings.extend(self._validate_region(resource))
            findings.extend(self._validate_configuration(resource))

        findings.extend(self._validate_dependencies(graph))
        findings.extend(self._validate_duplicates(graph))

        report = ValidationReport(findings=findings)

        logger.info(
            "validation_completed",
            resource_count=len(graph.resources),
            finding_count=len(findings),
            **{f"severity_{k}": v for k, v in report.summary.items()},
        )
        return report

    @staticmethod
    def _validate_naming(resource: CanonicalResource) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        name = resource.name

        if len(name) > 63:
            findings.append(ValidationFinding(
                check="naming.length",
                resource_id=resource.id,
                resource_name=name,
                severity=ValidationSeverity.ERROR,
                message=f"Resource name exceeds 63 characters ({len(name)} chars)",
                remediation="Shorten the resource name to 63 characters or fewer.",
            ))

        if name and not name[0].isalpha():
            findings.append(ValidationFinding(
                check="naming.start_with_letter",
                resource_id=resource.id,
                resource_name=name,
                severity=ValidationSeverity.WARNING,
                message="Resource name does not start with a letter",
                remediation="Rename to start with a lowercase letter.",
            ))

        return findings

    @staticmethod
    def _validate_cidr(resource: CanonicalResource) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        cidr_attrs = ["cidr_block", "ip_cidr_range"]

        for attr_name in cidr_attrs:
            cidr_value = resource.native_attributes.get(attr_name)
            if cidr_value and isinstance(cidr_value, str):
                try:
                    network = ipaddress.ip_network(cidr_value, strict=False)
                    # Warn on very large CIDR blocks
                    if network.prefixlen < 16:
                        findings.append(ValidationFinding(
                            check="cidr.too_large",
                            resource_id=resource.id,
                            resource_name=resource.name,
                            severity=ValidationSeverity.WARNING,
                            message=f"CIDR block {cidr_value} is very large (/{network.prefixlen})",
                            remediation="Consider using a smaller CIDR range to reduce blast radius.",
                        ))
                except ValueError:
                    findings.append(ValidationFinding(
                        check="cidr.invalid",
                        resource_id=resource.id,
                        resource_name=resource.name,
                        severity=ValidationSeverity.ERROR,
                        message=f"Invalid CIDR block: {cidr_value}",
                        remediation="Fix the CIDR notation to a valid format (e.g. 10.0.0.0/16).",
                    ))

        return findings

    @staticmethod
    def _validate_region(resource: CanonicalResource) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        if resource.region and resource.region != "global":
            from migration_factory.domain.enums import CloudProvider
            valid_regions = (
                _AWS_REGIONS if resource.source_provider is CloudProvider.AWS
                else _GCP_REGIONS
            )
            if resource.region not in valid_regions:
                findings.append(ValidationFinding(
                    check="region.unknown",
                    resource_id=resource.id,
                    resource_name=resource.name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Region '{resource.region}' is not in the known region list",
                    remediation="Verify the region is correct or update the validation catalog.",
                ))
        return findings

    @staticmethod
    def _validate_configuration(resource: CanonicalResource) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []

        # Check compute instances have required attributes
        if resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
            has_type = resource.native_attributes.get("instance_type") or resource.native_attributes.get("machine_type")
            if not has_type:
                findings.append(ValidationFinding(
                    check="config.missing_instance_type",
                    resource_id=resource.id,
                    resource_name=resource.name,
                    severity=ValidationSeverity.ERROR,
                    message="Compute instance missing instance_type/machine_type",
                    remediation="Specify the instance type in the resource attributes.",
                ))

        # Check databases have engine info
        if resource.canonical_type is CanonicalResourceType.DATABASE_INSTANCE:
            if not resource.native_attributes.get("engine") and not resource.native_attributes.get("database_version"):
                findings.append(ValidationFinding(
                    check="config.missing_db_engine",
                    resource_id=resource.id,
                    resource_name=resource.name,
                    severity=ValidationSeverity.WARNING,
                    message="Database instance missing engine/database_version",
                    remediation="Specify the database engine and version.",
                ))

        return findings

    @staticmethod
    def _validate_dependencies(graph: CanonicalInfrastructureGraph) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        dangling = graph.validate_references()
        for dep_id in dangling:
            # Find which resource references it
            referencing = [
                r.id for r in graph.resources.values()
                if dep_id in r.depends_on
            ]
            findings.append(ValidationFinding(
                check="dependency.dangling",
                resource_id=dep_id,
                resource_name=dep_id,
                severity=ValidationSeverity.WARNING,
                message=f"Referenced by {', '.join(referencing)} but not present in graph",
                remediation="Include the missing dependency in the migration scope or remove the reference.",
            ))

        # Cycle detection
        try:
            graph.topological_order()
        except Exception as exc:
            findings.append(ValidationFinding(
                check="dependency.circular",
                resource_id="graph",
                resource_name="dependency_graph",
                severity=ValidationSeverity.ERROR,
                message=f"Circular dependency detected: {exc}",
                remediation="Break the circular dependency by reviewing depends_on relationships.",
            ))

        return findings

    @staticmethod
    def _validate_duplicates(graph: CanonicalInfrastructureGraph) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        seen_names: dict[str, list[str]] = {}

        for resource in graph.resources.values():
            key = f"{resource.canonical_type.value}:{resource.name}"
            seen_names.setdefault(key, []).append(resource.id)

        for key, ids in seen_names.items():
            if len(ids) > 1:
                findings.append(ValidationFinding(
                    check="duplicate.name_and_type",
                    resource_id=ids[0],
                    resource_name=key,
                    severity=ValidationSeverity.WARNING,
                    message=f"Multiple resources with same name and type: {', '.join(ids)}",
                    remediation="Verify these are intentional duplicates; rename if not.",
                ))

        return findings
