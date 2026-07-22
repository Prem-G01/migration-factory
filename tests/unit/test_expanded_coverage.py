"""Tests for expanded AWS mapper coverage and capability matrix."""

from __future__ import annotations

from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.mappers.aws_to_canonical import AWSToCanonicalMapper
from migration_factory.parsers.base import ParsedResource
from migration_factory.translation.matrix import load_builtin_matrix


def _parsed(source_type, identifier="test.resource"):
    return ParsedResource(
        source_provider=CloudProvider.AWS,
        source_type=source_type,
        source_identifier=identifier,
        name="test",
        attributes={"id": "test-id"},
        raw_depends_on=[],
        source_path="test.tfstate",
    )


class TestExpandedAWSMapper:
    def setup_method(self):
        self.mapper = AWSToCanonicalMapper()

    def test_supports_all_30_plus_resource_types(self):
        supported = [
            "aws_vpc", "aws_subnet", "aws_security_group", "aws_nat_gateway",
            "aws_vpn_gateway", "aws_vpc_peering_connection", "aws_route_table",
            "aws_instance", "aws_lambda_function", "aws_eks_cluster",
            "aws_ecs_cluster", "aws_ecs_service",
            "aws_s3_bucket", "aws_ebs_volume", "aws_efs_file_system",
            "aws_db_instance", "aws_rds_cluster", "aws_dynamodb_table",
            "aws_elasticache_cluster",
            "aws_iam_role", "aws_iam_policy", "aws_secretsmanager_secret",
            "aws_acm_certificate",
            "aws_lb", "aws_alb", "aws_cloudfront_distribution",
            "aws_route53_zone", "aws_route53_record",
            "aws_sns_topic", "aws_sqs_queue",
            "aws_cloudwatch_metric_alarm", "aws_cloudwatch_log_group",
        ]
        for rt in supported:
            assert self.mapper.supports(rt), f"{rt} should be supported"

    def test_lambda_maps_to_serverless(self):
        canonical = self.mapper.map(_parsed("aws_lambda_function"))
        assert canonical.canonical_type is CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION

    def test_eks_maps_to_container_cluster(self):
        canonical = self.mapper.map(_parsed("aws_eks_cluster"))
        assert canonical.canonical_type is CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER

    def test_dynamodb_maps_to_nosql(self):
        canonical = self.mapper.map(_parsed("aws_dynamodb_table"))
        assert canonical.canonical_type is CanonicalResourceType.DATABASE_NOSQL

    def test_elasticache_maps_to_cache(self):
        canonical = self.mapper.map(_parsed("aws_elasticache_cluster"))
        assert canonical.canonical_type is CanonicalResourceType.DATABASE_CACHE

    def test_sns_maps_to_topic(self):
        canonical = self.mapper.map(_parsed("aws_sns_topic"))
        assert canonical.canonical_type is CanonicalResourceType.MESSAGING_TOPIC

    def test_sqs_maps_to_queue(self):
        canonical = self.mapper.map(_parsed("aws_sqs_queue"))
        assert canonical.canonical_type is CanonicalResourceType.MESSAGING_QUEUE

    def test_cloudfront_maps_to_cdn(self):
        canonical = self.mapper.map(_parsed("aws_cloudfront_distribution"))
        assert canonical.canonical_type is CanonicalResourceType.CDN_DISTRIBUTION

    def test_route53_zone_maps_to_dns_zone(self):
        canonical = self.mapper.map(_parsed("aws_route53_zone"))
        assert canonical.canonical_type is CanonicalResourceType.DNS_ZONE

    def test_secrets_manager_maps(self):
        canonical = self.mapper.map(_parsed("aws_secretsmanager_secret"))
        assert canonical.canonical_type is CanonicalResourceType.SECRETS_MANAGER

    def test_nat_gateway_maps(self):
        canonical = self.mapper.map(_parsed("aws_nat_gateway"))
        assert canonical.canonical_type is CanonicalResourceType.NETWORK_NAT_GATEWAY

    def test_efs_maps_to_file_system(self):
        canonical = self.mapper.map(_parsed("aws_efs_file_system"))
        assert canonical.canonical_type is CanonicalResourceType.STORAGE_FILE_SYSTEM

    def test_ebs_maps_to_block_volume(self):
        canonical = self.mapper.map(_parsed("aws_ebs_volume"))
        assert canonical.canonical_type is CanonicalResourceType.STORAGE_BLOCK_VOLUME


class TestExpandedCapabilityMatrix:
    def test_matrix_has_29_rules(self):
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        assert len(matrix.rules) == 29

    def test_every_rule_has_rationale(self):
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        for rule in matrix.rules:
            assert len(rule.rationale) >= 10, f"{rule.canonical_type}: needs real rationale"

    def test_every_rule_has_complexity_weight(self):
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        for rule in matrix.rules:
            assert 1 <= rule.complexity_weight <= 10

    def test_covers_all_non_unsupported_canonical_types(self):
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        covered = {rule.canonical_type for rule in matrix.rules}
        all_types = {ct for ct in CanonicalResourceType if ct is not CanonicalResourceType.UNSUPPORTED}
        uncovered = all_types - covered
        assert uncovered == set(), f"Missing matrix rules for: {uncovered}"
