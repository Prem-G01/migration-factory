from __future__ import annotations

import json
from pathlib import Path

import pytest

from migration_factory.core.exceptions import ParserError
from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.terraform_state import TerraformStateParser


@pytest.fixture
def parser() -> TerraformStateParser:
    return TerraformStateParser()


def test_supports_valid_tfstate(parser: TerraformStateParser, sample_tfstate_path: Path) -> None:
    assert parser.supports(sample_tfstate_path) is True


def test_supports_rejects_non_tfstate(parser: TerraformStateParser, tmp_path: Path) -> None:
    other = tmp_path / "notes.txt"
    other.write_text("hello")
    assert parser.supports(other) is False


def test_parses_all_managed_resources_and_skips_data_sources(
    parser: TerraformStateParser, sample_tfstate_path: Path
) -> None:
    result = parser.parse(sample_tfstate_path)

    # 6 managed resources in the fixture; 1 data source skipped.
    assert result.resource_count == 6
    assert {r.source_type for r in result.resources} == {
        "aws_vpc",
        "aws_subnet",
        "aws_security_group",
        "aws_instance",
        "aws_s3_bucket",
        "aws_iam_role",
    }
    assert all(r.source_provider is CloudProvider.AWS for r in result.resources)


def test_dependencies_captured_as_raw_terraform_addresses(
    parser: TerraformStateParser, sample_tfstate_path: Path
) -> None:
    result = parser.parse(sample_tfstate_path)
    instance = next(r for r in result.resources if r.source_type == "aws_instance")
    assert set(instance.raw_depends_on) == {"aws_subnet.app", "aws_security_group.app"}


def test_source_identifier_matches_terraform_address(
    parser: TerraformStateParser, sample_tfstate_path: Path
) -> None:
    result = parser.parse(sample_tfstate_path)
    vpc = next(r for r in result.resources if r.source_type == "aws_vpc")
    assert vpc.source_identifier == "aws_vpc.main"
    assert vpc.name == "vpc-0abc123"  # falls back to attributes["id"]


def test_invalid_json_raises_parser_error(parser: TerraformStateParser, tmp_path: Path) -> None:
    bad_file = tmp_path / "broken.tfstate"
    bad_file.write_text("{ not valid json")
    with pytest.raises(ParserError, match="not valid JSON"):
        parser.parse(bad_file)


def test_unsupported_format_version_raises(parser: TerraformStateParser, tmp_path: Path) -> None:
    bad_file = tmp_path / "old.tfstate"
    bad_file.write_text(json.dumps({"format_version": "3", "resources": []}))
    with pytest.raises(ParserError, match="Unsupported Terraform state format_version"):
        parser.parse(bad_file)


def test_malformed_resource_instance_becomes_warning_not_fatal(
    parser: TerraformStateParser, tmp_path: Path
) -> None:
    state = {
        "format_version": "4",
        "resources": [
            {
                "mode": "managed",
                "type": "aws_vpc",
                "name": "broken",
                "instances": [{}],  # malformed: missing required "attributes" key
            },
            {
                "mode": "managed",
                "type": "aws_vpc",
                "name": "good",
                "instances": [{"attributes": {"id": "vpc-good"}}],
            },
        ],
    }
    bad_file = tmp_path / "partial.tfstate"
    bad_file.write_text(json.dumps(state))

    result = parser.parse(bad_file)

    assert result.resource_count == 1
    assert result.resources[0].name == "vpc-good"
    assert len(result.warnings) == 1
    assert "broken" in (result.warnings[0].source_identifier or "")
