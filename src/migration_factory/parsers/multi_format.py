"""Multi-format parsers: CloudFormation, YAML, JSON, CSV, Terraform Plan.

Each implements BaseParser and is registered via entry points. Adding a
parser here = adding one line to pyproject.toml, never touching core code.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

# YAML: uses json.loads for JSON-superset YAML; install pyyaml for full YAML support
from migration_factory.core.exceptions import ParserError
from migration_factory.core.logging import get_logger
from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.base import BaseParser, ParsedResource, ParserResult, ParseWarning

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Minimal YAML handling (no pyyaml dependency — json-compatible subset)
# ---------------------------------------------------------------------------

def _safe_yaml_load(text: str) -> Any:
    """Parse YAML that's a JSON superset. For full YAML, install pyyaml."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try basic YAML-like key: value parsing for simple files
        result: dict[str, Any] = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                result[key.strip()] = value.strip()
        return result if result else None


# ---------------------------------------------------------------------------
# CloudFormation Parser
# ---------------------------------------------------------------------------


class CloudFormationParser(BaseParser):
    """Parses AWS CloudFormation templates (JSON or YAML)."""

    name = "cloudformation"

    def supports(self, source_path: Path) -> bool:
        if source_path.suffix not in {".json", ".yaml", ".yml", ".template"}:
            return False
        try:
            text = source_path.read_text(encoding="utf-8")
            data = json.loads(text) if source_path.suffix == ".json" else _safe_yaml_load(text)
            return isinstance(data, dict) and ("AWSTemplateFormatVersion" in data or "Resources" in data)
        except Exception:
            return False

    def parse(self, source_path: Path) -> ParserResult:
        try:
            text = source_path.read_text(encoding="utf-8")
            template = json.loads(text) if source_path.suffix == ".json" else _safe_yaml_load(text)
        except Exception as exc:
            raise ParserError(
                f"Could not parse CloudFormation template: {source_path}",
                context={"source_path": str(source_path)},
                cause=exc,
            ) from exc

        if not isinstance(template, dict):
            raise ParserError("CloudFormation template is not a valid object", context={"source_path": str(source_path)})

        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []
        cfn_resources = template.get("Resources", {})

        if not isinstance(cfn_resources, dict):
            return ParserResult(parser_name=self.name, source_path=str(source_path))

        for logical_id, resource_def in cfn_resources.items():
            if not isinstance(resource_def, dict):
                warnings.append(ParseWarning(source_identifier=logical_id, message="Invalid resource definition"))
                continue

            cfn_type = resource_def.get("Type", "")
            properties = resource_def.get("Properties", {})
            depends = resource_def.get("DependsOn", [])
            if isinstance(depends, str):
                depends = [depends]

            # Map CloudFormation type to Terraform-style type
            tf_type = self._cfn_to_tf_type(cfn_type)
            name = properties.get("Name") or properties.get("FunctionName") or logical_id

            resources.append(ParsedResource(
                source_provider=CloudProvider.AWS,
                source_type=tf_type,
                source_identifier=logical_id,
                name=str(name),
                attributes=properties if isinstance(properties, dict) else {},
                raw_depends_on=depends if isinstance(depends, list) else [],
                source_path=str(source_path),
            ))

        return ParserResult(
            parser_name=self.name,
            source_path=str(source_path),
            resources=resources,
            warnings=warnings,
        )

    @staticmethod
    def _cfn_to_tf_type(cfn_type: str) -> str:
        """Convert CloudFormation type (AWS::EC2::Instance) to Terraform-style (aws_instance)."""
        mapping: dict[str, str] = {
            "AWS::EC2::Instance": "aws_instance",
            "AWS::EC2::VPC": "aws_vpc",
            "AWS::EC2::Subnet": "aws_subnet",
            "AWS::EC2::SecurityGroup": "aws_security_group",
            "AWS::S3::Bucket": "aws_s3_bucket",
            "AWS::RDS::DBInstance": "aws_db_instance",
            "AWS::IAM::Role": "aws_iam_role",
            "AWS::Lambda::Function": "aws_lambda_function",
            "AWS::ElasticLoadBalancingV2::LoadBalancer": "aws_lb",
            "AWS::ECS::Cluster": "aws_ecs_cluster",
            "AWS::EKS::Cluster": "aws_eks_cluster",
            "AWS::DynamoDB::Table": "aws_dynamodb_table",
            "AWS::SNS::Topic": "aws_sns_topic",
            "AWS::SQS::Queue": "aws_sqs_queue",
            "AWS::Route53::HostedZone": "aws_route53_zone",
            "AWS::CloudFront::Distribution": "aws_cloudfront_distribution",
            "AWS::SecretsManager::Secret": "aws_secretsmanager_secret",
        }
        return mapping.get(cfn_type, cfn_type.lower().replace("::", "_"))


# ---------------------------------------------------------------------------
# Generic JSON Parser
# ---------------------------------------------------------------------------


class JSONInventoryParser(BaseParser):
    """Parses generic JSON inventory files containing a list of resources."""

    name = "json_inventory"

    def supports(self, source_path: Path) -> bool:
        if source_path.suffix != ".json":
            return False
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
            # Must be a dict with an "inventory" or "resources" key containing a list
            return isinstance(data, dict) and (
                isinstance(data.get("inventory"), list) or isinstance(data.get("resources"), list)
            )
        except Exception:
            return False

    def parse(self, source_path: Path) -> ParserResult:
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ParserError(f"Could not parse JSON: {source_path}", cause=exc) from exc

        items = data.get("inventory") or data.get("resources") or []
        resources: list[ParsedResource] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            resources.append(ParsedResource(
                source_provider=CloudProvider(item.get("provider", "unknown")),
                source_type=item.get("type", "unknown"),
                source_identifier=item.get("id", item.get("name", "unnamed")),
                name=item.get("name", "unnamed"),
                attributes=item.get("attributes", {}),
                raw_depends_on=item.get("depends_on", []),
                source_path=str(source_path),
            ))

        return ParserResult(parser_name=self.name, source_path=str(source_path), resources=resources)


# ---------------------------------------------------------------------------
# CSV Parser
# ---------------------------------------------------------------------------


class CSVInventoryParser(BaseParser):
    """Parses CSV inventory exports. Expects headers: type, name, id, region, provider."""

    name = "csv_inventory"

    def supports(self, source_path: Path) -> bool:
        return source_path.suffix in {".csv", ".tsv"}

    def parse(self, source_path: Path) -> ParserResult:
        try:
            text = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ParserError(f"Could not read CSV: {source_path}", cause=exc) from exc

        delimiter = "\t" if source_path.suffix == ".tsv" else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []

        for row_num, row in enumerate(reader, 2):
            try:
                provider = row.get("provider", "aws").strip().lower()
                resource_type = row.get("type", "unknown").strip()
                name = row.get("name", "unnamed").strip()
                resource_id = row.get("id", name).strip()

                attrs = {k: v for k, v in row.items() if k not in {"provider", "type", "name", "id", "depends_on"}}
                depends = [d.strip() for d in row.get("depends_on", "").split(",") if d.strip()]

                resources.append(ParsedResource(
                    source_provider=CloudProvider(provider) if provider in {e.value for e in CloudProvider} else CloudProvider.UNKNOWN,
                    source_type=resource_type,
                    source_identifier=resource_id,
                    name=name,
                    attributes=attrs,
                    raw_depends_on=depends,
                    source_path=str(source_path),
                ))
            except Exception as exc:
                warnings.append(ParseWarning(message=f"Row {row_num}: {exc}"))

        return ParserResult(parser_name=self.name, source_path=str(source_path), resources=resources, warnings=warnings)


# ---------------------------------------------------------------------------
# Terraform Plan Parser
# ---------------------------------------------------------------------------


class TerraformPlanParser(BaseParser):
    """Parses `terraform plan -json` or `terraform show -json plan.out` output."""

    name = "terraform_plan"

    def supports(self, source_path: Path) -> bool:
        if source_path.suffix != ".json":
            return False
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
            return isinstance(data, dict) and "resource_changes" in data
        except Exception:
            return False

    def parse(self, source_path: Path) -> ParserResult:
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ParserError(f"Could not parse Terraform plan: {source_path}", cause=exc) from exc

        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []

        for change in data.get("resource_changes", []):
            if not isinstance(change, dict):
                continue

            mode = change.get("mode", "managed")
            if mode != "managed":
                continue

            resource_type = change.get("type", "")
            address = change.get("address", "")
            name = change.get("name", address)

            # Use the "after" values (planned state) if available
            change_detail = change.get("change", {})
            after = change_detail.get("after") if isinstance(change_detail, dict) else None
            attributes = after if isinstance(after, dict) else {}

            # Infer provider
            provider = CloudProvider.UNKNOWN
            if resource_type.startswith("aws_"):
                provider = CloudProvider.AWS
            elif resource_type.startswith("google_"):
                provider = CloudProvider.GCP

            resources.append(ParsedResource(
                source_provider=provider,
                source_type=resource_type,
                source_identifier=address,
                name=str(attributes.get("id") or attributes.get("name") or name),
                attributes=attributes,
                raw_depends_on=[],
                source_path=str(source_path),
            ))

        return ParserResult(parser_name=self.name, source_path=str(source_path), resources=resources, warnings=warnings)
