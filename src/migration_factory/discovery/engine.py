"""Cloud Discovery Engine.

Enriches canonical resources with business metadata by auto-classifying
from tags, and provides a simulation-mode discovery that parses AWS CLI
JSON inventory exports (e.g., `aws ec2 describe-instances --output json`)
into ParsedResource records.

In production, this module would wrap boto3/google-cloud-sdk API calls
with pagination, rate limiting, and credential management. The current
implementation covers the data model and classification logic; the API
client layer is a separate engineering effort requiring cloud credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.exceptions import ParserError
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Tag-based auto-classification
# ---------------------------------------------------------------------------

_ENVIRONMENT_TAG_KEYS = {"Environment", "Env", "environment", "env", "Stage", "stage"}
_OWNER_TAG_KEYS = {"Owner", "owner", "Team", "team", "ManagedBy", "managed-by"}
_APPLICATION_TAG_KEYS = {"Application", "app", "App", "Service", "service", "Project", "project"}
_COST_CENTER_TAG_KEYS = {"CostCenter", "cost-center", "cost_center", "BillingCode"}
_CRITICALITY_TAG_KEYS = {"Criticality", "criticality", "Priority", "priority", "Tier", "tier"}

_CRITICALITY_NORMALIZATION: dict[str, str] = {
    "p1": "critical", "p2": "high", "p3": "medium", "p4": "low",
    "tier1": "critical", "tier2": "high", "tier3": "medium", "tier4": "low",
    "1": "critical", "2": "high", "3": "medium", "4": "low",
    "critical": "critical", "high": "high", "medium": "medium", "low": "low",
    "production": "critical", "staging": "medium", "development": "low",
}


class DiscoveryEnrichment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    fields_enriched: list[str] = Field(default_factory=list)
    source: str = "tag_classification"


class DiscoveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resources_enriched: int = 0
    enrichments: list[DiscoveryEnrichment] = Field(default_factory=list)
    unclassified_resources: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class DiscoveryEngine:
    """Enriches a canonical graph with business metadata extracted from tags."""

    def enrich(self, graph: CanonicalInfrastructureGraph) -> DiscoveryReport:
        """Auto-classify resources by examining their tags."""
        enrichments: list[DiscoveryEnrichment] = []
        unclassified: list[str] = []

        for resource in graph.resources.values():
            enriched_fields = self._classify_from_tags(resource)

            if enriched_fields:
                enrichments.append(DiscoveryEnrichment(
                    resource_id=resource.id,
                    fields_enriched=enriched_fields,
                ))
            else:
                unclassified.append(resource.id)

        report = DiscoveryReport(
            resources_enriched=len(enrichments),
            enrichments=enrichments,
            unclassified_resources=unclassified,
        )

        logger.info(
            "discovery_enrichment_completed",
            enriched=len(enrichments),
            unclassified=len(unclassified),
        )
        return report

    @staticmethod
    def _classify_from_tags(resource: CanonicalResource) -> list[str]:
        """Extract business metadata from resource tags."""
        enriched: list[str] = []
        tags = resource.tags

        # Environment
        if not resource.environment:
            for key in _ENVIRONMENT_TAG_KEYS:
                if key in tags:
                    resource.environment = tags[key].lower()
                    enriched.append("environment")
                    break

        # Owner
        if not resource.owner:
            for key in _OWNER_TAG_KEYS:
                if key in tags:
                    resource.owner = tags[key]
                    enriched.append("owner")
                    break

        # Application
        if not resource.application:
            for key in _APPLICATION_TAG_KEYS:
                if key in tags:
                    resource.application = tags[key]
                    enriched.append("application")
                    break

        # Cost center
        if not resource.cost_center:
            for key in _COST_CENTER_TAG_KEYS:
                if key in tags:
                    resource.cost_center = tags[key]
                    enriched.append("cost_center")
                    break

        # Criticality
        if not resource.criticality:
            for key in _CRITICALITY_TAG_KEYS:
                if key in tags:
                    raw = tags[key].lower().strip()
                    normalized = _CRITICALITY_NORMALIZATION.get(raw, raw)
                    resource.criticality = normalized
                    enriched.append("criticality")
                    break

            # Infer criticality from environment if not explicitly tagged
            if not resource.criticality and resource.environment:
                env_criticality = _CRITICALITY_NORMALIZATION.get(resource.environment)
                if env_criticality:
                    resource.criticality = env_criticality
                    enriched.append("criticality")

        return enriched


# ---------------------------------------------------------------------------
# AWS CLI inventory parser (simulation mode)
# ---------------------------------------------------------------------------


class InventoryParser:
    """Parses AWS CLI JSON output (e.g., describe-instances, describe-vpcs)
    into a format consumable by the existing Terraform State Parser
    infrastructure.

    This is the foundation for live discovery — the same data model that
    a boto3 API client would produce.
    """

    @staticmethod
    def parse_aws_ec2_instances(json_path: Path) -> list[dict[str, Any]]:
        """Parse `aws ec2 describe-instances` JSON output."""
        try:
            with json_path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ParserError(
                f"Could not parse AWS inventory file: {json_path}",
                context={"path": str(json_path)},
                cause=exc,
            ) from exc

        instances: list[dict[str, Any]] = []
        reservations = data.get("Reservations", [])

        for reservation in reservations:
            for instance in reservation.get("Instances", []):
                # Convert AWS API format to a canonical-compatible dict
                tags_list = instance.get("Tags", [])
                tags = {t["Key"]: t["Value"] for t in tags_list if "Key" in t and "Value" in t}
                name = tags.get("Name", instance.get("InstanceId", "unnamed"))

                instances.append({
                    "source_type": "aws_instance",
                    "source_identifier": instance.get("InstanceId", ""),
                    "name": name,
                    "attributes": {
                        "id": instance.get("InstanceId"),
                        "instance_type": instance.get("InstanceType"),
                        "availability_zone": instance.get("Placement", {}).get("AvailabilityZone"),
                        "subnet_id": instance.get("SubnetId"),
                        "vpc_security_group_ids": [
                            sg.get("GroupId") for sg in instance.get("SecurityGroups", [])
                        ],
                        "instance_state": instance.get("State", {}),
                        "tags": tags,
                    },
                })

        logger.info("aws_inventory_parsed", resource_type="ec2_instance", count=len(instances))
        return instances
