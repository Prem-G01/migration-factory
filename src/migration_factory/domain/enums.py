"""Provider-agnostic enumerations used throughout the Canonical Infrastructure Model.

`CanonicalResourceType` is intentionally a closed, curated set of categories
that every supported cloud maps INTO — it is not "one enum value per AWS
resource type". This is what makes AWS -> GCP (or any N x M cloud pair)
tractable: parsers/mappers translate provider-native types down to this
shared vocabulary, and generators translate back up to the target provider's
native resources. Adding a new provider means writing mappers in both
directions against this fixed vocabulary — it does not mean an M x N matrix
of point-to-point converters.
"""

from __future__ import annotations

from enum import StrEnum


class CloudProvider(StrEnum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"  # future
    UNKNOWN = "unknown"


class CanonicalResourceType(StrEnum):
    """Provider-agnostic resource categories.

    Extended in v0.4 to cover the resource families needed for real-world
    enterprise migrations: networking (VPC/subnet/firewall/NAT/VPN/peering),
    compute (instance/container/serverless), storage (object/block/file),
    database (relational/nosql/cache), security (IAM/secrets/certificates),
    application (load balancer/CDN/DNS/messaging/queue), and observability.
    """

    # Networking
    NETWORK_VPC = "network.vpc"
    NETWORK_SUBNET = "network.subnet"
    NETWORK_FIREWALL_RULE = "network.firewall_rule"
    NETWORK_NAT_GATEWAY = "network.nat_gateway"
    NETWORK_VPN = "network.vpn"
    NETWORK_PEERING = "network.peering"
    NETWORK_ROUTE_TABLE = "network.route_table"

    # Compute
    COMPUTE_INSTANCE = "compute.instance"
    COMPUTE_CONTAINER_CLUSTER = "compute.container_cluster"
    COMPUTE_SERVERLESS_FUNCTION = "compute.serverless_function"
    COMPUTE_CONTAINER_SERVICE = "compute.container_service"

    # Storage
    STORAGE_OBJECT_BUCKET = "storage.object_bucket"
    STORAGE_BLOCK_VOLUME = "storage.block_volume"
    STORAGE_FILE_SYSTEM = "storage.file_system"

    # Database
    DATABASE_INSTANCE = "database.instance"
    DATABASE_NOSQL = "database.nosql"
    DATABASE_CACHE = "database.cache"

    # Security / IAM
    IAM_ROLE = "iam.role"
    IAM_POLICY = "iam.policy"
    SECRETS_MANAGER = "secrets.manager"
    CERTIFICATE = "security.certificate"

    # Application services
    LOAD_BALANCER = "load_balancer"
    CDN_DISTRIBUTION = "cdn.distribution"
    DNS_ZONE = "dns.zone"
    DNS_RECORD = "dns.record"
    MESSAGING_TOPIC = "messaging.topic"
    MESSAGING_QUEUE = "messaging.queue"

    # Observability
    MONITORING_ALARM = "monitoring.alarm"
    LOG_GROUP = "monitoring.log_group"

    UNSUPPORTED = "unsupported"


class ResourceLifecycleState(StrEnum):
    """Where a canonical resource sits in the migration lifecycle."""

    DISCOVERED = "discovered"
    VALIDATED = "validated"
    MAPPED = "mapped"
    GENERATED = "generated"
    DEPLOYED = "deployed"
    FAILED = "failed"
