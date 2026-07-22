from __future__ import annotations

from pathlib import Path

from migration_factory.core.config import Settings
from migration_factory.domain.enums import CanonicalResourceType
from migration_factory.pipeline import IngestionPipeline


def test_full_pipeline_parses_and_normalizes_sample_estate(sample_tfstate_path: Path) -> None:
    pipeline = IngestionPipeline(settings=Settings())
    report = pipeline.run(sample_tfstate_path)

    assert report.parser_used == "terraform_state"
    assert len(report.graph.resources) == 6
    assert report.unsupported_resources == []
    assert report.dangling_dependencies == []
    assert report.parse_warnings == []


def test_pipeline_deployment_order_places_vpc_before_dependents(
    sample_tfstate_path: Path,
) -> None:
    pipeline = IngestionPipeline(settings=Settings())
    report = pipeline.run(sample_tfstate_path)

    order = report.graph.topological_order()
    vpc_id = "aws:aws_vpc.main"
    subnet_id = "aws:aws_subnet.app"
    instance_id = "aws:aws_instance.app"

    assert order.index(vpc_id) < order.index(subnet_id) < order.index(instance_id)


def test_pipeline_canonical_types_are_correct(sample_tfstate_path: Path) -> None:
    pipeline = IngestionPipeline(settings=Settings())
    report = pipeline.run(sample_tfstate_path)

    types_by_id = {rid: r.canonical_type for rid, r in report.graph.resources.items()}
    assert types_by_id["aws:aws_vpc.main"] is CanonicalResourceType.NETWORK_VPC
    assert types_by_id["aws:aws_instance.app"] is CanonicalResourceType.COMPUTE_INSTANCE
    assert types_by_id["aws:aws_s3_bucket.artifacts"] is CanonicalResourceType.STORAGE_OBJECT_BUCKET
    assert types_by_id["aws:aws_iam_role.app_role"] is CanonicalResourceType.IAM_ROLE


def test_pipeline_records_unsupported_resource_instead_of_crashing(tmp_path: Path) -> None:
    import json

    state = {
        "format_version": "4",
        "resources": [
            {
                "mode": "managed",
                "type": "aws_totally_unsupported_thing",
                "name": "x",
                "instances": [{"attributes": {"id": "x-1"}}],
            },
            {
                "mode": "managed",
                "type": "aws_vpc",
                "name": "main",
                "instances": [{"attributes": {"id": "vpc-1"}}],
            },
        ],
    }
    state_file = tmp_path / "mixed.tfstate"
    state_file.write_text(json.dumps(state))

    settings = Settings()
    assert settings.parsing.fail_on_unsupported_resource is False  # default

    pipeline = IngestionPipeline(settings=settings)
    report = pipeline.run(state_file)

    assert len(report.graph.resources) == 1
    assert report.unsupported_resources == ["aws_totally_unsupported_thing.x"]
    assert report.is_clean is False
