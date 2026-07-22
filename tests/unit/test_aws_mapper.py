from __future__ import annotations

import pytest

from migration_factory.core.exceptions import MappingError
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.mappers.aws_to_canonical import AWSToCanonicalMapper
from migration_factory.parsers.base import ParsedResource


@pytest.fixture
def mapper() -> AWSToCanonicalMapper:
    return AWSToCanonicalMapper()


def _parsed(
    source_type: str,
    *,
    identifier: str,
    attributes: dict[str, object],
    raw_depends_on: list[str] | None = None,
) -> ParsedResource:
    return ParsedResource(
        source_provider=CloudProvider.AWS,
        source_type=source_type,
        source_identifier=identifier,
        name=str(attributes.get("id", identifier)),
        attributes=attributes,
        raw_depends_on=raw_depends_on or [],
        source_path="test.tfstate",
    )


def test_supports_known_types(mapper: AWSToCanonicalMapper) -> None:
    assert mapper.supports("aws_vpc") is True
    assert mapper.supports("aws_totally_made_up_type") is False


def test_maps_vpc_to_network_vpc(mapper: AWSToCanonicalMapper) -> None:
    parsed = _parsed(
        "aws_vpc",
        identifier="aws_vpc.main",
        attributes={"id": "vpc-123", "tags": {"Name": "main"}},
    )
    canonical = mapper.map(parsed)

    assert canonical.canonical_type is CanonicalResourceType.NETWORK_VPC
    assert canonical.id == "aws:aws_vpc.main"
    assert canonical.tags == {"Name": "main"}
    assert canonical.native_attributes == parsed.attributes


def test_maps_instance_and_derives_region_from_az(mapper: AWSToCanonicalMapper) -> None:
    parsed = _parsed(
        "aws_instance",
        identifier="aws_instance.app",
        attributes={"id": "i-123", "availability_zone": "us-east-1a"},
        raw_depends_on=["aws_subnet.app", "aws_security_group.app"],
    )
    canonical = mapper.map(parsed)

    assert canonical.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE
    assert canonical.region == "us-east-1"
    assert canonical.depends_on == frozenset({"aws:aws_subnet.app", "aws:aws_security_group.app"})


def test_maps_iam_role_to_global_region(mapper: AWSToCanonicalMapper) -> None:
    parsed = _parsed(
        "aws_iam_role",
        identifier="aws_iam_role.app_role",
        attributes={"id": "app-role", "name": "app-role"},
    )
    canonical = mapper.map(parsed)

    assert canonical.canonical_type is CanonicalResourceType.IAM_ROLE
    assert canonical.region == "global"


def test_unsupported_type_raises_mapping_error(mapper: AWSToCanonicalMapper) -> None:
    parsed = _parsed(
        "aws_totally_made_up_type",
        identifier="aws_totally_made_up_type.x",
        attributes={"id": "x"},
    )
    with pytest.raises(MappingError, match="No AWS mapping registered"):
        mapper.map(parsed)


def test_missing_tags_defaults_to_empty_dict(mapper: AWSToCanonicalMapper) -> None:
    parsed = _parsed("aws_vpc", identifier="aws_vpc.no_tags", attributes={"id": "vpc-456"})
    canonical = mapper.map(parsed)
    assert canonical.tags == {}
