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
from migration_factory.parsers.column_detection import build_resource_from_row

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
    """Parses CSV inventory exports.

    Tries the canonical `type,name,id,provider,region` headers first, then
    falls back to ~20 real-world column aliases (InstanceId, ResourceType,
    Asset Type, ...) and infers whatever it still can't find a column for
    — see `column_detection.py`.
    """

    name = "csv_inventory"

    def supports(self, source_path: Path) -> bool:
        return source_path.suffix in {".csv", ".tsv"}

    def parse(self, source_path: Path) -> ParserResult:
        try:
            # utf-8-sig strips a leading BOM (common in Excel-exported CSVs)
            # instead of leaving it glued to the first header's name.
            text = source_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ParserError(f"Could not read CSV: {source_path}", cause=exc) from exc

        delimiter = "\t" if source_path.suffix == ".tsv" else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []

        for row_num, row in enumerate(reader, 2):
            try:
                # DictReader: missing trailing fields -> None; a `None` key
                # holds any ragged extra fields beyond the header count.
                clean_row = {k.strip(): (v or "") for k, v in row.items() if k}
                resource = build_resource_from_row(clean_row, row_num, str(source_path))
                if resource is None:
                    continue  # blank row
                resources.append(resource)
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


# ---------------------------------------------------------------------------
# AWS CLI JSON Output Parser
# ---------------------------------------------------------------------------


def _tag_value(tags: list[dict[str, Any]] | None, key: str) -> str | None:
    for t in tags or []:
        if isinstance(t, dict) and t.get("Key") == key:
            value = t.get("Value")
            return str(value) if value is not None else None
    return None


class AWSCLIOutputParser(BaseParser):
    """Parses raw JSON straight from `aws <service> describe-*`/`list-*`
    CLI commands — no reshaping needed. A single file may combine several
    commands' output (e.g. Reservations + Vpcs + Subnets all present), and
    the flattened `--query 'Reservations[].Instances[]'` list form is
    handled too.
    """

    name = "aws_cli_output"

    _TOP_LEVEL_KEYS = (
        "Reservations", "Vpcs", "Subnets", "SecurityGroups", "Buckets",
        "DBInstances", "Roles", "Functions", "Clusters", "LoadBalancers",
        "Topics", "QueueUrls",
    )
    _QUERY_INSTANCE_KEYS = {"InstanceId", "InstanceType"}

    def supports(self, source_path: Path) -> bool:
        if source_path.suffix != ".json":
            return False
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception:
            return False

        if isinstance(data, dict):
            return any(k in data for k in self._TOP_LEVEL_KEYS)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return self._QUERY_INSTANCE_KEYS.issubset(data[0].keys())
        return False

    def parse(self, source_path: Path) -> ParserResult:
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ParserError(f"Could not parse AWS CLI JSON output: {source_path}", cause=exc) from exc

        path_str = str(source_path)
        resources: list[ParsedResource] = []

        if isinstance(data, list):
            # `--query 'Reservations[].Instances[]'` flat instance list.
            resources.extend(self._instance_to_resource(item, path_str) for item in data if isinstance(item, dict))
            return ParserResult(parser_name=self.name, source_path=path_str, resources=resources)

        if not isinstance(data, dict):
            raise ParserError(f"AWS CLI JSON output is not an object or list: {source_path}", context={"source_path": path_str})

        for reservation in data.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                resources.append(self._instance_to_resource(instance, path_str))
        for vpc in data.get("Vpcs", []):
            resources.append(self._vpc_to_resource(vpc, path_str))
        for subnet in data.get("Subnets", []):
            resources.append(self._subnet_to_resource(subnet, path_str))
        for sg in data.get("SecurityGroups", []):
            resources.append(self._sg_to_resource(sg, path_str))
        for bucket in data.get("Buckets", []):
            resources.append(self._bucket_to_resource(bucket, path_str))
        for db in data.get("DBInstances", []):
            resources.append(self._db_to_resource(db, path_str))
        for role in data.get("Roles", []):
            resources.append(self._role_to_resource(role, path_str))
        for fn in data.get("Functions", []):
            resources.append(self._function_to_resource(fn, path_str))
        for cluster in data.get("Clusters", []):
            resources.append(self._cluster_to_resource(cluster, path_str))
        for lb in data.get("LoadBalancers", []):
            resources.append(self._lb_to_resource(lb, path_str))
        for topic in data.get("Topics", []):
            resources.append(self._topic_to_resource(topic, path_str))
        for url in data.get("QueueUrls", []):
            if isinstance(url, str):
                resources.append(self._queue_to_resource(url, path_str))

        return ParserResult(parser_name=self.name, source_path=path_str, resources=resources)

    @staticmethod
    def _instance_to_resource(instance: dict[str, Any], source_path: str) -> ParsedResource:
        tags = instance.get("Tags", [])
        instance_id = str(instance.get("InstanceId", "unknown"))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_instance",
            source_identifier=instance_id,
            name=_tag_value(tags, "Name") or instance_id,
            attributes={
                "instance_type": instance.get("InstanceType"),
                "state": (instance.get("State") or {}).get("Name"),
                "vpc_id": instance.get("VpcId"),
                "subnet_id": instance.get("SubnetId"),
                "private_ip": instance.get("PrivateIpAddress"),
                "public_ip": instance.get("PublicIpAddress"),
                "availability_zone": (instance.get("Placement") or {}).get("AvailabilityZone"),
                "security_groups": [sg.get("GroupId") for sg in instance.get("SecurityGroups", []) if isinstance(sg, dict)],
                "tags": {t.get("Key"): t.get("Value") for t in tags if isinstance(t, dict)},
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _vpc_to_resource(vpc: dict[str, Any], source_path: str) -> ParsedResource:
        tags = vpc.get("Tags", [])
        vpc_id = str(vpc.get("VpcId", "unknown"))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_vpc",
            source_identifier=vpc_id,
            name=_tag_value(tags, "Name") or vpc_id,
            attributes={
                "cidr_block": vpc.get("CidrBlock"),
                "is_default": vpc.get("IsDefault"),
                "tags": {t.get("Key"): t.get("Value") for t in tags if isinstance(t, dict)},
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _subnet_to_resource(subnet: dict[str, Any], source_path: str) -> ParsedResource:
        tags = subnet.get("Tags", [])
        subnet_id = str(subnet.get("SubnetId", "unknown"))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_subnet",
            source_identifier=subnet_id,
            name=_tag_value(tags, "Name") or subnet_id,
            attributes={
                "cidr_block": subnet.get("CidrBlock"),
                "vpc_id": subnet.get("VpcId"),
                "az": subnet.get("AvailabilityZone"),
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _sg_to_resource(sg: dict[str, Any], source_path: str) -> ParsedResource:
        group_id = str(sg.get("GroupId", "unknown"))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_security_group",
            source_identifier=group_id,
            name=str(sg.get("GroupName", group_id)),
            attributes={
                "description": sg.get("Description"),
                "vpc_id": sg.get("VpcId"),
                "ingress": sg.get("IpPermissions"),
                "egress": sg.get("IpPermissionsEgress"),
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _bucket_to_resource(bucket: dict[str, Any], source_path: str) -> ParsedResource:
        name = str(bucket.get("Name", "unknown"))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_s3_bucket",
            source_identifier=name,
            name=name,
            attributes={"creation_date": bucket.get("CreationDate")},
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _db_to_resource(db: dict[str, Any], source_path: str) -> ParsedResource:
        identifier = str(db.get("DBInstanceIdentifier", "unknown"))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_db_instance",
            source_identifier=identifier,
            name=identifier,
            attributes={
                "engine": db.get("Engine"),
                "instance_class": db.get("DBInstanceClass"),
                "allocated_storage": db.get("AllocatedStorage"),
                "multi_az": db.get("MultiAZ"),
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _role_to_resource(role: dict[str, Any], source_path: str) -> ParsedResource:
        role_id = str(role.get("RoleId", role.get("RoleName", "unknown")))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_iam_role",
            source_identifier=role_id,
            name=str(role.get("RoleName", role_id)),
            attributes={
                "arn": role.get("Arn"),
                "path": role.get("Path"),
                "assume_role_policy": role.get("AssumeRolePolicyDocument"),
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _function_to_resource(fn: dict[str, Any], source_path: str) -> ParsedResource:
        arn = str(fn.get("FunctionArn", fn.get("FunctionName", "unknown")))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_lambda_function",
            source_identifier=arn,
            name=str(fn.get("FunctionName", arn)),
            attributes={
                "runtime": fn.get("Runtime"),
                "handler": fn.get("Handler"),
                "memory_size": fn.get("MemorySize"),
                "timeout": fn.get("Timeout"),
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _cluster_to_resource(cluster: Any, source_path: str) -> ParsedResource:
        # `aws eks list-clusters` returns bare name strings; combining it
        # with `describe-cluster` output (a dict per cluster) also works.
        if isinstance(cluster, str):
            return ParsedResource(
                source_provider=CloudProvider.AWS,
                source_type="aws_eks_cluster",
                source_identifier=cluster,
                name=cluster,
                attributes={},
                raw_depends_on=[],
                source_path=source_path,
            )
        name = str(cluster.get("name", cluster.get("arn", "unknown")))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_eks_cluster",
            source_identifier=str(cluster.get("arn", name)),
            name=name,
            attributes={"status": cluster.get("status"), "version": cluster.get("version")},
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _lb_to_resource(lb: dict[str, Any], source_path: str) -> ParsedResource:
        arn = str(lb.get("LoadBalancerArn", lb.get("LoadBalancerName", "unknown")))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_lb",
            source_identifier=arn,
            name=str(lb.get("LoadBalancerName", arn)),
            attributes={
                "type": lb.get("Type"),
                "scheme": lb.get("Scheme"),
                "vpc_id": lb.get("VpcId"),
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _topic_to_resource(topic: dict[str, Any], source_path: str) -> ParsedResource:
        arn = str(topic.get("TopicArn", "unknown"))
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_sns_topic",
            source_identifier=arn,
            name=arn.split(":")[-1] if arn != "unknown" else arn,
            attributes={"arn": arn},
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _queue_to_resource(url: str, source_path: str) -> ParsedResource:
        return ParsedResource(
            source_provider=CloudProvider.AWS,
            source_type="aws_sqs_queue",
            source_identifier=url,
            name=url.rstrip("/").split("/")[-1] if url else "unknown",
            attributes={"url": url},
            raw_depends_on=[],
            source_path=source_path,
        )


# ---------------------------------------------------------------------------
# GCP CLI JSON Output Parser
# ---------------------------------------------------------------------------


class GCPCLIOutputParser(BaseParser):
    """Parses raw JSON from `gcloud <group> list --format json` commands: a
    plain JSON list (the normal gcloud shape), or the GCP REST-API
    `{"items": [...]}` wrapper some exports use instead.
    """

    name = "gcp_cli_output"

    def supports(self, source_path: Path) -> bool:
        if source_path.suffix != ".json":
            return False
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return self._classify(data) is not None

    def parse(self, source_path: Path) -> ParserResult:
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ParserError(f"Could not parse gcloud JSON output: {source_path}", cause=exc) from exc

        kind = self._classify(data)
        if kind is None:
            raise ParserError(
                f"Unrecognized gcloud JSON output shape: {source_path}",
                context={"source_path": str(source_path)},
            )

        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = []

        converters = {
            "instance": self._instance_to_resource,
            "network": self._network_to_resource,
            "bucket": self._bucket_to_resource,
            "sql": self._sql_to_resource,
        }
        converter = converters[kind]

        resources = [converter(item, str(source_path)) for item in items if isinstance(item, dict)]
        return ParserResult(parser_name=self.name, source_path=str(source_path), resources=resources)

    @staticmethod
    def _classify(data: Any) -> str | None:
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            return None

        first = items[0]
        keys = {str(k).lower() for k in first}
        kind_str = str(first.get("kind", "")).lower()

        if "compute#instance" in kind_str or {"machinetype", "zone"}.issubset(keys):
            return "instance"
        if "compute#network" in kind_str or "autocreatesubnetworks" in keys:
            return "network"
        if "storage#bucket" in kind_str or ({"storageclass", "location"}.issubset(keys) and "name" in keys):
            return "bucket"
        if "sqladmin#" in kind_str or "databaseversion" in keys:
            return "sql"
        return None

    @staticmethod
    def _instance_to_resource(item: dict[str, Any], source_path: str) -> ParsedResource:
        name = str(item.get("name", "unknown"))
        machine_type = item.get("machineType", "")
        zone = item.get("zone", "")
        return ParsedResource(
            source_provider=CloudProvider.GCP,
            source_type="google_compute_instance",
            source_identifier=name,
            name=name,
            attributes={
                "machine_type": machine_type.rsplit("/", 1)[-1] if isinstance(machine_type, str) else machine_type,
                "zone": zone.rsplit("/", 1)[-1] if isinstance(zone, str) else zone,
                "status": item.get("status"),
                "labels": item.get("labels", {}),
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _network_to_resource(item: dict[str, Any], source_path: str) -> ParsedResource:
        name = str(item.get("name", "unknown"))
        return ParsedResource(
            source_provider=CloudProvider.GCP,
            source_type="google_compute_network",
            source_identifier=name,
            name=name,
            attributes={
                "auto_create_subnetworks": item.get("autoCreateSubnetworks"),
                "subnetworks": item.get("subnetworks", []),
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _bucket_to_resource(item: dict[str, Any], source_path: str) -> ParsedResource:
        name = str(item.get("name", "unknown"))
        return ParsedResource(
            source_provider=CloudProvider.GCP,
            source_type="google_storage_bucket",
            source_identifier=name,
            name=name,
            attributes={
                "location": item.get("location"),
                "storage_class": item.get("storageClass"),
                "labels": item.get("labels", {}),
            },
            raw_depends_on=[],
            source_path=source_path,
        )

    @staticmethod
    def _sql_to_resource(item: dict[str, Any], source_path: str) -> ParsedResource:
        name = str(item.get("name", "unknown"))
        settings_raw = item.get("settings")
        settings: dict[str, Any] = settings_raw if isinstance(settings_raw, dict) else {}
        return ParsedResource(
            source_provider=CloudProvider.GCP,
            source_type="google_sql_database_instance",
            source_identifier=name,
            name=name,
            attributes={
                "database_version": item.get("databaseVersion"),
                "region": item.get("region"),
                "tier": settings.get("tier"),
            },
            raw_depends_on=[],
            source_path=source_path,
        )
