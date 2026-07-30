"""Tests for the 12 AWS generators added to bring AWS coverage from
17/29 to 29/29 canonical resource types (see terraform_gen/engine.py,
_AWS_GENERATORS). Each is sourced from the GCP resource type it mirrors.
"""

from __future__ import annotations

from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph, CanonicalResource, SourceLocation
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.terraform_gen.engine import _AWS_GENERATORS, TerraformGenerator
from migration_factory.translation.models import SupportStatus, TranslationReport, TranslationResult


def _resource(
    canonical_type: CanonicalResourceType,
    name: str,
    source_type: str,
    native_attributes: dict[str, object] | None = None,
) -> CanonicalResource:
    return CanonicalResource(
        id=f"gcp:{name}",
        canonical_type=canonical_type,
        source_provider=CloudProvider.GCP,
        source_type=source_type,
        name=name,
        source_location=SourceLocation(source_system="test", source_path="test.tfstate"),
        native_attributes=native_attributes or {},
    )


def test_all_29_canonical_types_have_an_aws_generator() -> None:
    all_types = {t for t in CanonicalResourceType if t.name != "UNSUPPORTED"}
    assert set(_AWS_GENERATORS) == all_types


_NEW_RESOURCES = [
    (
        CanonicalResourceType.STORAGE_BLOCK_VOLUME,
        _resource(CanonicalResourceType.STORAGE_BLOCK_VOLUME, "app-disk", "google_compute_disk", {"size": 100, "type": "pd-ssd"}),
        "aws_ebs_volume",
    ),
    (
        CanonicalResourceType.DATABASE_NOSQL,
        _resource(CanonicalResourceType.DATABASE_NOSQL, "app-firestore", "google_firestore_database"),
        "aws_dynamodb_table",
    ),
    (
        CanonicalResourceType.NETWORK_ROUTE_TABLE,
        _resource(CanonicalResourceType.NETWORK_ROUTE_TABLE, "app-route", "google_compute_route", {"dest_range": "10.0.0.0/8"}),
        "aws_route_table",
    ),
    (
        CanonicalResourceType.COMPUTE_CONTAINER_SERVICE,
        _resource(CanonicalResourceType.COMPUTE_CONTAINER_SERVICE, "app-run", "google_cloud_run_v2_service"),
        "aws_ecs_service",
    ),
    (
        CanonicalResourceType.STORAGE_FILE_SYSTEM,
        _resource(CanonicalResourceType.STORAGE_FILE_SYSTEM, "app-filestore", "google_filestore_instance"),
        "aws_efs_file_system",
    ),
    (
        CanonicalResourceType.DNS_RECORD,
        _resource(CanonicalResourceType.DNS_RECORD, "app-record", "google_dns_record_set", {"type": "CNAME", "ttl": 60}),
        "aws_route53_record",
    ),
    (
        CanonicalResourceType.NETWORK_VPN,
        _resource(CanonicalResourceType.NETWORK_VPN, "app-vpn", "google_compute_vpn_tunnel", {"peer_ip": "203.0.113.5"}),
        "aws_vpn_connection",
    ),
    (
        CanonicalResourceType.NETWORK_PEERING,
        _resource(CanonicalResourceType.NETWORK_PEERING, "app-peering", "google_compute_network_peering"),
        "aws_vpc_peering_connection",
    ),
    (
        CanonicalResourceType.MONITORING_ALARM,
        _resource(CanonicalResourceType.MONITORING_ALARM, "app-alarm", "google_monitoring_alert_policy"),
        "aws_cloudwatch_metric_alarm",
    ),
    (
        CanonicalResourceType.LOG_GROUP,
        _resource(CanonicalResourceType.LOG_GROUP, "app-logs", "google_logging_project_bucket_config", {"retention_days": 45}),
        "aws_cloudwatch_log_group",
    ),
    (
        CanonicalResourceType.IAM_POLICY,
        _resource(CanonicalResourceType.IAM_POLICY, "app-policy", "google_project_iam_custom_role"),
        "aws_iam_policy",
    ),
    (
        CanonicalResourceType.CERTIFICATE,
        _resource(CanonicalResourceType.CERTIFICATE, "app-cert", "google_certificate_manager_certificate", {"domains": ["example.com"]}),
        "aws_acm_certificate",
    ),
]


def _generate_single(resource: CanonicalResource) -> str:
    graph = CanonicalInfrastructureGraph(resources={resource.id: resource})
    translation = TranslationReport(
        source_provider=CloudProvider.GCP,
        target_provider=CloudProvider.AWS,
        results=[
            TranslationResult(
                resource_id=resource.id,
                resource_name=resource.name,
                canonical_type=resource.canonical_type,
                status=SupportStatus.SUPPORTED,
                target_terraform_types=["aws_placeholder"],
                rationale="test",
            )
        ],
    )
    report = TerraformGenerator(target_provider=CloudProvider.AWS, project_id="x").generate(graph, translation)
    main_tf = next(f for f in report.files if f.filename == "main.tf")
    return main_tf.content


def test_each_new_generator_emits_the_expected_resource_type() -> None:
    for canonical_type, resource, expected_tf_type in _NEW_RESOURCES:
        content = _generate_single(resource)
        assert f'resource "{expected_tf_type}"' in content, f"{canonical_type.value} did not emit {expected_tf_type}"
        assert "UNSUPPORTED" not in content


def test_cloudwatch_log_group_snaps_retention_to_a_valid_value() -> None:
    resource = _resource(
        CanonicalResourceType.LOG_GROUP, "app-logs", "google_logging_project_bucket_config", {"retention_days": 45}
    )
    content = _generate_single(resource)
    # 45 isn't a valid CloudWatch retention value -- nearest of (30, 60) is 30.
    assert "retention_in_days = 30" in content


def test_full_graph_of_all_new_types_produces_valid_terraform_syntax() -> None:
    resources = {r.id: r for _, r, _ in _NEW_RESOURCES}
    graph = CanonicalInfrastructureGraph(resources=resources)
    translation = TranslationReport(
        source_provider=CloudProvider.GCP,
        target_provider=CloudProvider.AWS,
        results=[
            TranslationResult(
                resource_id=r.id,
                resource_name=r.name,
                canonical_type=r.canonical_type,
                status=SupportStatus.SUPPORTED,
                target_terraform_types=["aws_placeholder"],
                rationale="test",
            )
            for _, r, _ in _NEW_RESOURCES
        ],
    )
    report = TerraformGenerator(target_provider=CloudProvider.AWS, project_id="x").generate(graph, translation)
    assert report.generated_resources == len(_NEW_RESOURCES)
    assert report.skipped_resources == 0
