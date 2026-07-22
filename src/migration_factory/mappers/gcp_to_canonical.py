"""GCP -> Canonical Mapper.

Maps google_* Terraform resource types into the Canonical Infrastructure
Model, mirroring the AWS mapper's structure. Registered via entry points.
"""

from __future__ import annotations

from collections.abc import Callable

from migration_factory.core.exceptions import MappingError
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalResource, SourceLocation
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.mappers.base import BaseMapper
from migration_factory.parsers.base import ParsedResource

logger = get_logger(__name__)


def _canonical_id(parsed: ParsedResource) -> str:
    return f"{parsed.source_provider.value}:{parsed.source_identifier}"


def _depends_on(parsed: ParsedResource) -> frozenset[str]:
    return frozenset(f"{parsed.source_provider.value}:{addr}" for addr in parsed.raw_depends_on)


def _tags(attributes: dict[str, object]) -> dict[str, str]:
    raw = attributes.get("labels") or attributes.get("tags") or {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _region(attributes: dict[str, object]) -> str | None:
    return str(attributes.get("region") or attributes.get("location") or "") or None


_GCP_HANDLERS: dict[str, Callable[[ParsedResource], tuple[CanonicalResourceType, str | None]]] = {
    "google_compute_network": lambda p: (CanonicalResourceType.NETWORK_VPC, None),
    "google_compute_subnetwork": lambda p: (CanonicalResourceType.NETWORK_SUBNET, _region(p.attributes)),
    "google_compute_firewall": lambda p: (CanonicalResourceType.NETWORK_FIREWALL_RULE, None),
    "google_compute_router_nat": lambda p: (CanonicalResourceType.NETWORK_NAT_GATEWAY, _region(p.attributes)),
    "google_compute_vpn_tunnel": lambda p: (CanonicalResourceType.NETWORK_VPN, _region(p.attributes)),
    "google_compute_network_peering": lambda p: (CanonicalResourceType.NETWORK_PEERING, None),
    "google_compute_route": lambda p: (CanonicalResourceType.NETWORK_ROUTE_TABLE, None),
    "google_compute_instance": lambda p: (CanonicalResourceType.COMPUTE_INSTANCE, p.attributes.get("zone", "")),
    "google_container_cluster": lambda p: (CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER, _region(p.attributes)),
    "google_cloudfunctions2_function": lambda p: (CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION, _region(p.attributes)),
    "google_cloud_run_v2_service": lambda p: (CanonicalResourceType.COMPUTE_CONTAINER_SERVICE, _region(p.attributes)),
    "google_storage_bucket": lambda p: (CanonicalResourceType.STORAGE_OBJECT_BUCKET, _region(p.attributes)),
    "google_compute_disk": lambda p: (CanonicalResourceType.STORAGE_BLOCK_VOLUME, None),
    "google_filestore_instance": lambda p: (CanonicalResourceType.STORAGE_FILE_SYSTEM, _region(p.attributes)),
    "google_sql_database_instance": lambda p: (CanonicalResourceType.DATABASE_INSTANCE, _region(p.attributes)),
    "google_firestore_database": lambda p: (CanonicalResourceType.DATABASE_NOSQL, _region(p.attributes)),
    "google_redis_instance": lambda p: (CanonicalResourceType.DATABASE_CACHE, _region(p.attributes)),
    "google_service_account": lambda p: (CanonicalResourceType.IAM_ROLE, "global"),
    "google_project_iam_custom_role": lambda p: (CanonicalResourceType.IAM_POLICY, "global"),
    "google_secret_manager_secret": lambda p: (CanonicalResourceType.SECRETS_MANAGER, None),
    "google_certificate_manager_certificate": lambda p: (CanonicalResourceType.CERTIFICATE, None),
    "google_compute_global_forwarding_rule": lambda p: (CanonicalResourceType.LOAD_BALANCER, "global"),
    "google_compute_backend_bucket": lambda p: (CanonicalResourceType.CDN_DISTRIBUTION, "global"),
    "google_dns_managed_zone": lambda p: (CanonicalResourceType.DNS_ZONE, "global"),
    "google_dns_record_set": lambda p: (CanonicalResourceType.DNS_RECORD, "global"),
    "google_pubsub_topic": lambda p: (CanonicalResourceType.MESSAGING_TOPIC, None),
    "google_cloud_tasks_queue": lambda p: (CanonicalResourceType.MESSAGING_QUEUE, _region(p.attributes)),
    "google_monitoring_alert_policy": lambda p: (CanonicalResourceType.MONITORING_ALARM, None),
    "google_logging_project_bucket_config": lambda p: (CanonicalResourceType.LOG_GROUP, None),
}


class GCPToCanonicalMapper(BaseMapper):
    name = "gcp_to_canonical"

    def supports(self, source_type: str) -> bool:
        return source_type in _GCP_HANDLERS

    def map(self, parsed: ParsedResource) -> CanonicalResource:
        handler = _GCP_HANDLERS.get(parsed.source_type)
        if handler is None:
            raise MappingError(
                f"No GCP mapping for {parsed.source_type!r}",
                context={"source_type": parsed.source_type, "supported": sorted(_GCP_HANDLERS)},
            )

        canonical_type, region = handler(parsed)
        return CanonicalResource(
            id=_canonical_id(parsed),
            canonical_type=canonical_type,
            source_provider=CloudProvider.GCP,
            source_type=parsed.source_type,
            name=parsed.name,
            region=str(region) if region else None,
            tags=_tags(parsed.attributes),
            depends_on=_depends_on(parsed),
            native_attributes=parsed.attributes,
            source_location=SourceLocation(
                source_system="terraform_state",
                source_path=parsed.source_path,
                source_identifier=parsed.source_identifier,
            ),
        )
