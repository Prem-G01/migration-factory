"""GCP Live Discovery Module.

Full google-cloud SDK based resource discovery covering all canonical
resource types. Activated by providing GCP credentials.

Required: pip install google-cloud-compute google-cloud-storage
          google-cloud-container google-cloud-dns
Credentials: gcloud auth application-default login, or
             GOOGLE_APPLICATION_CREDENTIALS env var pointing to SA key file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.base import ParsedResource

logger = get_logger(__name__)


class GCPDiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: CloudProvider = CloudProvider.GCP
    project_id: str
    resources: list[ParsedResource] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    resource_counts: dict[str, int] = Field(default_factory=dict)
    mode: str = "live"


def _parsed(
    resource_type: str, resource_id: str, name: str,
    attributes: dict[str, Any], project: str
) -> ParsedResource:
    return ParsedResource(
        source_provider=CloudProvider.GCP,
        source_type=resource_type,
        source_identifier=resource_id,
        name=name,
        attributes=attributes,
        raw_depends_on=[],
        source_path=f"gcp_discovery:{project}",
    )


@dataclass(slots=True)
class GCPLiveDiscovery:
    """Full google-cloud SDK based GCP resource discovery."""

    project_id: str = "my-project"
    regions: list[str] = field(default_factory=lambda: ["us-central1"])
    simulation: bool = False

    def discover_all(self) -> GCPDiscoveryResult:
        """Discover all resources in the configured project."""
        if self.simulation:
            return self._simulate()

        resources: list[ParsedResource] = []
        errors: list[str] = []
        counts: dict[str, int] = {}

        discoverers = [
            ("google_compute_network", self._discover_networks),
            ("google_compute_subnetwork", self._discover_subnetworks),
            ("google_compute_firewall", self._discover_firewalls),
            ("google_compute_instance", self._discover_instances),
            ("google_storage_bucket", self._discover_buckets),
            ("google_sql_database_instance", self._discover_sql_instances),
            ("google_container_cluster", self._discover_gke_clusters),
            ("google_service_account", self._discover_service_accounts),
            ("google_pubsub_topic", self._discover_pubsub_topics),
            ("google_dns_managed_zone", self._discover_dns_zones),
            ("google_compute_router_nat", self._discover_cloud_nat),
        ]

        for rtype, fn in discoverers:
            try:
                discovered = fn()
                resources.extend(discovered)
                counts[rtype] = len(discovered)
            except Exception as exc:
                errors.append(f"{rtype}: {exc}")
                logger.warning("gcp_discovery_error", resource_type=rtype, error=str(exc))

        logger.info("gcp_discovery_completed", project=self.project_id, total=len(resources))
        return GCPDiscoveryResult(
            project_id=self.project_id, resources=resources,
            errors=errors, resource_counts=counts,
        )

    def _discover_networks(self) -> list[ParsedResource]:
        from google.cloud import compute_v1
        client = compute_v1.NetworksClient()
        result = []
        for net in client.list(project=self.project_id):
            result.append(_parsed(
                "google_compute_network", str(net.id), net.name,
                {"name": net.name, "auto_create_subnetworks": net.auto_create_subnetworks,
                 "id": str(net.id)}, self.project_id,
            ))
        return result

    def _discover_subnetworks(self) -> list[ParsedResource]:
        from google.cloud import compute_v1
        client = compute_v1.SubnetworksClient()
        result = []
        for region in self.regions:
            try:
                for sub in client.list(project=self.project_id, region=region):
                    result.append(_parsed(
                        "google_compute_subnetwork", str(sub.id), sub.name,
                        {"name": sub.name, "ip_cidr_range": sub.ip_cidr_range,
                         "region": region, "id": str(sub.id)}, self.project_id,
                    ))
            except Exception:
                pass
        return result

    def _discover_firewalls(self) -> list[ParsedResource]:
        from google.cloud import compute_v1
        client = compute_v1.FirewallsClient()
        result = []
        for fw in client.list(project=self.project_id):
            result.append(_parsed(
                "google_compute_firewall", str(fw.id), fw.name,
                {"name": fw.name, "network": fw.network, "direction": fw.direction,
                 "id": str(fw.id)}, self.project_id,
            ))
        return result

    def _discover_instances(self) -> list[ParsedResource]:
        from google.cloud import compute_v1
        client = compute_v1.InstancesClient()
        result = []
        for region in self.regions:
            for zone_suffix in ["a", "b", "c"]:
                zone = f"{region}-{zone_suffix}"
                try:
                    for inst in client.list(project=self.project_id, zone=zone):
                        result.append(_parsed(
                            "google_compute_instance", str(inst.id), inst.name,
                            {"name": inst.name, "machine_type": inst.machine_type,
                             "zone": zone, "status": inst.status,
                             "labels": dict(inst.labels), "id": str(inst.id)}, self.project_id,
                        ))
                except Exception:
                    pass
        return result

    def _discover_buckets(self) -> list[ParsedResource]:
        from google.cloud import storage
        client = storage.Client(project=self.project_id)
        result = []
        for bucket in client.list_buckets():
            result.append(_parsed(
                "google_storage_bucket", bucket.name, bucket.name,
                {"name": bucket.name, "location": bucket.location,
                 "storage_class": bucket.storage_class,
                 "labels": dict(bucket.labels) if bucket.labels else {}}, self.project_id,
            ))
        return result

    def _discover_sql_instances(self) -> list[ParsedResource]:
        from googleapiclient import discovery
        service = discovery.build("sqladmin", "v1")
        result_list = []
        try:
            resp = service.instances().list(project=self.project_id).execute()
            for inst in resp.get("items", []):
                result_list.append(_parsed(
                    "google_sql_database_instance", inst["name"], inst["name"],
                    {"database_version": inst.get("databaseVersion"),
                     "tier": inst.get("settings", {}).get("tier"),
                     "region": inst.get("region"), "id": inst["name"]}, self.project_id,
                ))
        except Exception:
            pass
        return result_list

    def _discover_gke_clusters(self) -> list[ParsedResource]:
        from google.cloud import container_v1
        client = container_v1.ClusterManagerClient()
        result = []
        for region in self.regions:
            try:
                parent = f"projects/{self.project_id}/locations/{region}"
                resp = client.list_clusters(parent=parent)
                for cluster in resp.clusters:
                    result.append(_parsed(
                        "google_container_cluster", cluster.self_link, cluster.name,
                        {"name": cluster.name, "location": region,
                         "initial_node_count": cluster.initial_node_count,
                         "status": cluster.status, "id": cluster.name}, self.project_id,
                    ))
            except Exception:
                pass
        return result

    def _discover_service_accounts(self) -> list[ParsedResource]:
        from googleapiclient import discovery
        service = discovery.build("iam", "v1")
        result_list = []
        try:
            resp = service.projects().serviceAccounts().list(
                name=f"projects/{self.project_id}"
            ).execute()
            for sa in resp.get("accounts", []):
                result_list.append(_parsed(
                    "google_service_account", sa["uniqueId"], sa["displayName"] or sa["email"],
                    {"email": sa["email"], "display_name": sa.get("displayName"),
                     "id": sa["uniqueId"]}, self.project_id,
                ))
        except Exception:
            pass
        return result_list

    def _discover_pubsub_topics(self) -> list[ParsedResource]:
        from google.cloud import pubsub_v1
        client = pubsub_v1.PublisherClient()
        project_path = f"projects/{self.project_id}"
        result = []
        try:
            for topic in client.list_topics(request={"project": project_path}):
                name = topic.name.split("/")[-1]
                result.append(_parsed(
                    "google_pubsub_topic", topic.name, name,
                    {"name": topic.name, "id": topic.name}, self.project_id,
                ))
        except Exception:
            pass
        return result

    def _discover_dns_zones(self) -> list[ParsedResource]:
        from google.cloud import dns
        client = dns.Client(project=self.project_id)
        result = []
        try:
            for zone in client.list_zones():
                result.append(_parsed(
                    "google_dns_managed_zone", zone.name, zone.name,
                    {"dns_name": zone.dns_name, "id": zone.name}, self.project_id,
                ))
        except Exception:
            pass
        return result

    def _discover_cloud_nat(self) -> list[ParsedResource]:
        from google.cloud import compute_v1
        client = compute_v1.RoutersClient()
        result = []
        for region in self.regions:
            try:
                for router in client.list(project=self.project_id, region=region):
                    for nat in router.nats:
                        result.append(_parsed(
                            "google_compute_router_nat", f"{router.name}/{nat.name}", nat.name,
                            {"router": router.name, "region": region, "id": nat.name}, self.project_id,
                        ))
            except Exception:
                pass
        return result

    def _simulate(self) -> GCPDiscoveryResult:
        from migration_factory.discovery.providers.cloud import GCPDiscovery
        sim = GCPDiscovery(simulation=True, project_id=self.project_id)
        result = sim.discover(regions=self.regions)
        parsed = sim.to_parsed_resources(result)
        return GCPDiscoveryResult(
            project_id=self.project_id, resources=parsed,
            resource_counts={r.source_type: 1 for r in parsed}, mode="simulation",
        )
