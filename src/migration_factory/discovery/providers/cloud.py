"""Cloud Discovery Providers.

Abstract interface for live cloud resource discovery + concrete
implementations for AWS (boto3) and GCP (google-cloud). Each provider
has a simulation mode that returns realistic mock data when credentials
are unavailable — the platform works end-to-end without cloud access.

Production: set CLOUD_DISCOVERY_MODE=live and provide credentials.
Development: default simulation mode returns mock inventories.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.base import ParsedResource

logger = get_logger(__name__)


class DiscoveredResource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: str
    resource_id: str
    name: str
    region: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)


class DiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: CloudProvider
    resources: list[DiscoveredResource] = Field(default_factory=list)
    regions_scanned: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    mode: str = "simulation"


class BaseCloudDiscovery(ABC):
    @abstractmethod
    def discover(self, regions: list[str] | None = None) -> DiscoveryResult:
        raise NotImplementedError

    @abstractmethod
    def to_parsed_resources(self, result: DiscoveryResult) -> list[ParsedResource]:
        raise NotImplementedError


@dataclass(slots=True)
class AWSDiscovery(BaseCloudDiscovery):
    """AWS resource discovery via boto3 (falls back to simulation)."""
    simulation: bool = True
    profile: str | None = None

    def discover(self, regions: list[str] | None = None) -> DiscoveryResult:
        target_regions = regions or ["us-east-1"]

        if not self.simulation:
            return self._live_discover(target_regions)
        return self._simulate(target_regions)

    def _live_discover(self, regions: list[str]) -> DiscoveryResult:
        """Live AWS discovery using boto3."""
        resources: list[DiscoveredResource] = []
        errors: list[str] = []

        try:
            import boto3
        except ImportError:
            return DiscoveryResult(
                provider=CloudProvider.AWS, errors=["boto3 not installed"], regions_scanned=regions, mode="error"
            )

        for region in regions:
            try:
                session = boto3.Session(profile_name=self.profile, region_name=region)

                # EC2 instances
                ec2 = session.client("ec2")
                for reservation in ec2.describe_instances().get("Reservations", []):
                    for inst in reservation.get("Instances", []):
                        tags = {t["Key"]: t["Value"] for t in inst.get("Tags", []) if "Key" in t}
                        resources.append(DiscoveredResource(
                            resource_type="aws_instance", resource_id=inst["InstanceId"],
                            name=tags.get("Name", inst["InstanceId"]), region=region,
                            attributes={"instance_type": inst.get("InstanceType"), "state": inst.get("State", {}).get("Name")},
                            tags=tags,
                        ))

                # VPCs
                for vpc in ec2.describe_vpcs().get("Vpcs", []):
                    tags = {t["Key"]: t["Value"] for t in vpc.get("Tags", []) if "Key" in t}
                    resources.append(DiscoveredResource(
                        resource_type="aws_vpc", resource_id=vpc["VpcId"],
                        name=tags.get("Name", vpc["VpcId"]), region=region,
                        attributes={"cidr_block": vpc.get("CidrBlock")}, tags=tags,
                    ))

                # S3 buckets (global, only scan once)
                if region == regions[0]:
                    s3 = session.client("s3")
                    for bucket in s3.list_buckets().get("Buckets", []):
                        resources.append(DiscoveredResource(
                            resource_type="aws_s3_bucket", resource_id=bucket["Name"],
                            name=bucket["Name"], region="global",
                        ))

            except Exception as exc:
                errors.append(f"{region}: {exc}")
                logger.warning("aws_discovery_error", region=region, error=str(exc))

        logger.info("aws_discovery_completed", resource_count=len(resources), region_count=len(regions))
        return DiscoveryResult(provider=CloudProvider.AWS, resources=resources, regions_scanned=regions, errors=errors, mode="live")

    @staticmethod
    def _simulate(regions: list[str]) -> DiscoveryResult:
        resources = [
            DiscoveredResource(resource_type="aws_vpc", resource_id="vpc-sim001", name="main-vpc", region=regions[0],
                attributes={"cidr_block": "10.0.0.0/16"}, tags={"Environment": "prod", "Owner": "platform"}),
            DiscoveredResource(resource_type="aws_subnet", resource_id="subnet-sim001", name="app-subnet", region=regions[0],
                attributes={"cidr_block": "10.0.1.0/24", "vpc_id": "vpc-sim001"}),
            DiscoveredResource(resource_type="aws_instance", resource_id="i-sim001", name="app-server", region=regions[0],
                attributes={"instance_type": "t3.medium", "state": "running"}, tags={"Environment": "prod", "Application": "web-api"}),
            DiscoveredResource(resource_type="aws_s3_bucket", resource_id="sim-data-bucket", name="sim-data-bucket", region="global"),
            DiscoveredResource(resource_type="aws_db_instance", resource_id="db-sim001", name="app-db", region=regions[0],
                attributes={"engine": "postgres", "instance_class": "db.t3.medium"}),
            DiscoveredResource(resource_type="aws_iam_role", resource_id="app-role", name="app-execution-role", region="global"),
        ]
        return DiscoveryResult(provider=CloudProvider.AWS, resources=resources, regions_scanned=regions, mode="simulation")

    def to_parsed_resources(self, result: DiscoveryResult) -> list[ParsedResource]:
        return [
            ParsedResource(
                source_provider=CloudProvider.AWS, source_type=r.resource_type,
                source_identifier=r.resource_id, name=r.name,
                attributes={**r.attributes, "tags": r.tags}, raw_depends_on=[], source_path="aws_discovery",
            ) for r in result.resources
        ]


@dataclass(slots=True)
class GCPDiscovery(BaseCloudDiscovery):
    """GCP resource discovery via google-cloud SDK (falls back to simulation)."""
    simulation: bool = True
    project_id: str = "my-project"

    def discover(self, regions: list[str] | None = None) -> DiscoveryResult:
        target_regions = regions or ["us-central1"]

        if not self.simulation:
            return self._live_discover(target_regions)
        return self._simulate(target_regions)

    def _live_discover(self, regions: list[str]) -> DiscoveryResult:
        resources: list[DiscoveredResource] = []
        errors: list[str] = []

        try:
            from google.cloud import compute_v1, storage
        except ImportError:
            return DiscoveryResult(
                provider=CloudProvider.GCP, errors=["google-cloud SDK not installed"], regions_scanned=regions, mode="error"
            )

        try:
            # Compute instances
            client = compute_v1.InstancesClient()
            for region in regions:
                for zone_suffix in ["a", "b", "c"]:
                    zone = f"{region}-{zone_suffix}"
                    try:
                        for inst in client.list(project=self.project_id, zone=zone):
                            resources.append(DiscoveredResource(
                                resource_type="google_compute_instance", resource_id=str(inst.id),
                                name=inst.name, region=region,
                                attributes={"machine_type": inst.machine_type, "status": inst.status},
                                tags=dict(inst.labels) if inst.labels else {},
                            ))
                    except Exception:
                        pass

            # GCS buckets
            storage_client = storage.Client(project=self.project_id)
            for bucket in storage_client.list_buckets():
                resources.append(DiscoveredResource(
                    resource_type="google_storage_bucket", resource_id=bucket.name,
                    name=bucket.name, region=bucket.location or "US",
                    tags=dict(bucket.labels) if bucket.labels else {},
                ))
        except Exception as exc:
            errors.append(str(exc))

        return DiscoveryResult(provider=CloudProvider.GCP, resources=resources, regions_scanned=regions, errors=errors, mode="live")

    @staticmethod
    def _simulate(regions: list[str]) -> DiscoveryResult:
        resources = [
            DiscoveredResource(resource_type="google_compute_network", resource_id="net-sim001", name="main-network", region="global"),
            DiscoveredResource(resource_type="google_compute_subnetwork", resource_id="sub-sim001", name="app-subnet", region=regions[0],
                attributes={"ip_cidr_range": "10.0.1.0/24"}),
            DiscoveredResource(resource_type="google_compute_instance", resource_id="inst-sim001", name="app-vm", region=regions[0],
                attributes={"machine_type": "e2-medium", "status": "RUNNING"}, tags={"environment": "prod"}),
            DiscoveredResource(resource_type="google_storage_bucket", resource_id="sim-gcs-bucket", name="sim-gcs-bucket", region="US"),
            DiscoveredResource(resource_type="google_sql_database_instance", resource_id="sql-sim001", name="app-db", region=regions[0],
                attributes={"database_version": "POSTGRES_14"}),
        ]
        return DiscoveryResult(provider=CloudProvider.GCP, resources=resources, regions_scanned=regions, mode="simulation")

    def to_parsed_resources(self, result: DiscoveryResult) -> list[ParsedResource]:
        return [
            ParsedResource(
                source_provider=CloudProvider.GCP, source_type=r.resource_type,
                source_identifier=r.resource_id, name=r.name,
                attributes={**r.attributes, "labels": r.tags}, raw_depends_on=[], source_path="gcp_discovery",
            ) for r in result.resources
        ]
