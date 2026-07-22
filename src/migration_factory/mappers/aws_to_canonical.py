"""AWS -> Canonical Mapper.

Covers the resource types needed for the AWS -> GCP vertical slice:
network (VPC/subnet/security group), compute (EC2 instance), storage (S3),
database (RDS instance), IAM (role), and load balancing (ALB/NLB). Extending
coverage is additive: register a new handler in `_HANDLERS`, never modify
existing handlers — this keeps every resource type's mapping independently
reviewable and testable.

Canonical id scheme: `f"{provider}:{terraform_address}"`, e.g.
`"aws:aws_vpc.main"`. This is deliberate: `ParsedResource.raw_depends_on`
contains Terraform addresses of same-provider resources in the *same* parse,
so dependency edges are derivable with simple string formatting — no second
graph-resolution pass is required inside the mapper. (Cross-state / cross-
provider dependency resolution is the Dependency Engine's job in Phase 2 and
operates on the assembled graph, not inside individual mappers.)
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

_Handler = Callable[[ParsedResource], CanonicalResourceType]


def _canonical_id(parsed: ParsedResource) -> str:
    return f"{parsed.source_provider.value}:{parsed.source_identifier}"


def _depends_on(parsed: ParsedResource) -> frozenset[str]:
    return frozenset(f"{parsed.source_provider.value}:{addr}" for addr in parsed.raw_depends_on)


def _tags(attributes: dict[str, object]) -> dict[str, str]:
    raw_tags = attributes.get("tags") or attributes.get("tags_all") or {}
    if not isinstance(raw_tags, dict):
        return {}
    return {str(k): str(v) for k, v in raw_tags.items()}


def _region_from_az(attributes: dict[str, object]) -> str | None:
    az = attributes.get("availability_zone")
    if isinstance(az, str) and az:
        return az[:-1]  # "us-east-1a" -> "us-east-1"
    return None


# ---------------------------------------------------------------------------
# Per-resource-type handlers: each returns just the CanonicalResourceType +
# region, since id/name/tags/depends_on/native_attributes are assembled
# uniformly by `map()` below. Handlers only encode what's genuinely
# type-specific: the canonical category and how region is derived.
# ---------------------------------------------------------------------------


def _map_vpc(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.NETWORK_VPC, None


def _map_subnet(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.NETWORK_SUBNET, _region_from_az(parsed.attributes)


def _map_security_group(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.NETWORK_FIREWALL_RULE, None


def _map_instance(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.COMPUTE_INSTANCE, _region_from_az(parsed.attributes)


def _map_s3_bucket(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    region = parsed.attributes.get("region")
    return CanonicalResourceType.STORAGE_OBJECT_BUCKET, str(region) if region else None


def _map_db_instance(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.DATABASE_INSTANCE, _region_from_az(parsed.attributes)


def _map_iam_role(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.IAM_ROLE, "global"


def _map_lb(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    region = parsed.attributes.get("region")
    return CanonicalResourceType.LOAD_BALANCER, str(region) if region else None


# --- Extended resource type handlers (v0.4) ---

def _map_nat_gateway(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.NETWORK_NAT_GATEWAY, _region_from_az(parsed.attributes)


def _map_vpn(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.NETWORK_VPN, None


def _map_peering(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.NETWORK_PEERING, None


def _map_route_table(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.NETWORK_ROUTE_TABLE, None


def _map_lambda(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION, None


def _map_eks(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER, None


def _map_ecs(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.COMPUTE_CONTAINER_SERVICE, None


def _map_ebs(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.STORAGE_BLOCK_VOLUME, _region_from_az(parsed.attributes)


def _map_efs(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.STORAGE_FILE_SYSTEM, None


def _map_dynamodb(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.DATABASE_NOSQL, None


def _map_elasticache(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.DATABASE_CACHE, _region_from_az(parsed.attributes)


def _map_iam_policy(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.IAM_POLICY, "global"


def _map_iam_role_policy_attachment(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    # `role` holds the role name/ARN (the AWS provider schema has no `role_arn`
    # attribute on this resource); fall back to it when `role_arn` isn't present.
    role_arn = parsed.attributes.get("role_arn") or parsed.attributes.get("role")
    policy_arn = parsed.attributes.get("policy_arn")
    logger.debug(
        "iam_role_policy_attachment_mapped",
        role_arn=role_arn,
        policy_arn=policy_arn,
    )
    return CanonicalResourceType.IAM_POLICY, "global"


def _map_secretsmanager(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.SECRETS_MANAGER, None


def _map_acm(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.CERTIFICATE, None


def _map_cloudfront(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.CDN_DISTRIBUTION, "global"


def _map_route53_zone(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.DNS_ZONE, "global"


def _map_route53_record(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.DNS_RECORD, "global"


def _map_sns(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.MESSAGING_TOPIC, None


def _map_sqs(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.MESSAGING_QUEUE, None


def _map_cloudwatch_alarm(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.MONITORING_ALARM, None


def _map_cloudwatch_log(parsed: ParsedResource) -> tuple[CanonicalResourceType, str | None]:
    return CanonicalResourceType.LOG_GROUP, None


_HANDLERS: dict[str, Callable[[ParsedResource], tuple[CanonicalResourceType, str | None]]] = {
    # Networking
    "aws_vpc": _map_vpc,
    "aws_subnet": _map_subnet,
    "aws_security_group": _map_security_group,
    "aws_nat_gateway": _map_nat_gateway,
    "aws_vpn_gateway": _map_vpn,
    "aws_vpn_connection": _map_vpn,
    "aws_vpc_peering_connection": _map_peering,
    "aws_route_table": _map_route_table,
    # Compute
    "aws_instance": _map_instance,
    "aws_lambda_function": _map_lambda,
    "aws_eks_cluster": _map_eks,
    "aws_ecs_cluster": _map_ecs,
    "aws_ecs_service": _map_ecs,
    # Storage
    "aws_s3_bucket": _map_s3_bucket,
    "aws_ebs_volume": _map_ebs,
    "aws_efs_file_system": _map_efs,
    # Database
    "aws_db_instance": _map_db_instance,
    "aws_rds_cluster": _map_db_instance,
    "aws_dynamodb_table": _map_dynamodb,
    "aws_elasticache_cluster": _map_elasticache,
    "aws_elasticache_replication_group": _map_elasticache,
    # IAM / Security
    "aws_iam_role": _map_iam_role,
    "aws_iam_policy": _map_iam_policy,
    "aws_iam_role_policy_attachment": _map_iam_role_policy_attachment,
    "aws_secretsmanager_secret": _map_secretsmanager,
    "aws_acm_certificate": _map_acm,
    # Application services
    "aws_lb": _map_lb,
    "aws_alb": _map_lb,
    "aws_cloudfront_distribution": _map_cloudfront,
    "aws_route53_zone": _map_route53_zone,
    "aws_route53_record": _map_route53_record,
    "aws_sns_topic": _map_sns,
    "aws_sqs_queue": _map_sqs,
    # Monitoring
    "aws_cloudwatch_metric_alarm": _map_cloudwatch_alarm,
    "aws_cloudwatch_log_group": _map_cloudwatch_log,
}


class AWSToCanonicalMapper(BaseMapper):
    name = "aws_to_canonical"

    def supports(self, source_type: str) -> bool:
        return source_type in _HANDLERS

    def map(self, parsed: ParsedResource) -> CanonicalResource:
        handler = _HANDLERS.get(parsed.source_type)
        if handler is None:
            raise MappingError(
                f"No AWS mapping registered for resource type {parsed.source_type!r}",
                context={
                    "source_type": parsed.source_type,
                    "source_identifier": parsed.source_identifier,
                    "supported_types": sorted(_HANDLERS),
                },
                remediation="Add a handler to _HANDLERS in aws_to_canonical.py, or set "
                "parsing.fail_on_unsupported_resource=False to record this as a "
                "warning and continue.",
            )

        canonical_type, region = handler(parsed)

        resource = CanonicalResource(
            id=_canonical_id(parsed),
            canonical_type=canonical_type,
            source_provider=CloudProvider.AWS,
            source_type=parsed.source_type,
            name=parsed.name,
            region=region,
            tags=_tags(parsed.attributes),
            depends_on=_depends_on(parsed),
            native_attributes=parsed.attributes,
            source_location=SourceLocation(
                source_system="terraform_state",
                source_path=parsed.source_path,
                source_identifier=parsed.source_identifier,
            ),
        )

        logger.debug(
            "resource_mapped",
            source_type=parsed.source_type,
            canonical_type=canonical_type.value,
            canonical_id=resource.id,
        )
        return resource
