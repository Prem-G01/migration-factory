"""AWS Live Discovery Module.

Full boto3-based cloud resource discovery covering all canonical resource
types. Activated by setting simulation=False and providing AWS credentials
via environment variables or IAM instance profile.

Required: pip install boto3
Credentials: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY, or AWS profile,
             or IAM instance profile (when running on EC2/ECS/Lambda).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.base import ParsedResource

logger = get_logger(__name__)


class AWSResourcePage(BaseModel):
    """A page of discovered AWS resources with pagination metadata."""
    model_config = ConfigDict(extra="forbid")
    resource_type: str
    resources: list[dict[str, Any]] = Field(default_factory=list)
    region: str = ""
    next_token: str | None = None


class AWSDiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: CloudProvider = CloudProvider.AWS
    region: str
    resources: list[ParsedResource] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    resource_counts: dict[str, int] = Field(default_factory=dict)
    mode: str = "live"


def _tags_dict(tag_list: list[dict[str, str]]) -> dict[str, str]:
    return {t.get("Key", ""): t.get("Value", "") for t in tag_list if "Key" in t}


def _parsed(
    resource_type: str, resource_id: str, name: str,
    attributes: dict[str, Any], region: str, source: str = "aws_discovery"
) -> ParsedResource:
    return ParsedResource(
        source_provider=CloudProvider.AWS,
        source_type=resource_type,
        source_identifier=resource_id,
        name=name,
        attributes=attributes,
        raw_depends_on=[],
        source_path=source,
    )


@dataclass(slots=True)
class AWSLiveDiscovery:
    """Full boto3-based AWS resource discovery."""

    profile: str | None = None
    regions: list[str] = field(default_factory=lambda: ["us-east-1"])
    simulation: bool = False

    def _session(self, region: str) -> Any:
        try:
            import boto3
            return boto3.Session(profile_name=self.profile, region_name=region)
        except ImportError as exc:
            raise RuntimeError("boto3 required: pip install boto3") from exc

    def discover_all(self) -> list[AWSDiscoveryResult]:
        """Discover all resources across all configured regions."""
        if self.simulation:
            return self._simulate()
        return [self.discover_region(r) for r in self.regions]

    def discover_region(self, region: str) -> AWSDiscoveryResult:
        """Discover all resources in a single region."""
        resources: list[ParsedResource] = []
        errors: list[str] = []
        counts: dict[str, int] = {}

        discoverers = [
            ("aws_vpc", self._discover_vpcs),
            ("aws_subnet", self._discover_subnets),
            ("aws_security_group", self._discover_security_groups),
            ("aws_instance", self._discover_instances),
            ("aws_s3_bucket", self._discover_s3_buckets),
            ("aws_db_instance", self._discover_rds_instances),
            ("aws_iam_role", self._discover_iam_roles),
            ("aws_lambda_function", self._discover_lambda_functions),
            ("aws_eks_cluster", self._discover_eks_clusters),
            ("aws_lb", self._discover_load_balancers),
            ("aws_sns_topic", self._discover_sns_topics),
            ("aws_sqs_queue", self._discover_sqs_queues),
            ("aws_cloudwatch_metric_alarm", self._discover_cloudwatch_alarms),
            ("aws_route53_zone", self._discover_route53_zones),
        ]

        for rtype, fn in discoverers:
            try:
                discovered = fn(region)
                resources.extend(discovered)
                counts[rtype] = len(discovered)
            except Exception as exc:
                errors.append(f"{rtype} in {region}: {exc}")
                logger.warning("aws_discovery_resource_error", resource_type=rtype, region=region, error=str(exc))

        logger.info("aws_region_discovered", region=region, total=len(resources), errors=len(errors))
        return AWSDiscoveryResult(region=region, resources=resources, errors=errors, resource_counts=counts)

    def _discover_vpcs(self, region: str) -> list[ParsedResource]:
        ec2 = self._session(region).client("ec2")
        result = []
        for vpc in ec2.describe_vpcs().get("Vpcs", []):
            tags = _tags_dict(vpc.get("Tags", []))
            result.append(_parsed(
                "aws_vpc", vpc["VpcId"], tags.get("Name", vpc["VpcId"]),
                {"cidr_block": vpc.get("CidrBlock"), "id": vpc["VpcId"], "tags": tags}, region,
            ))
        return result

    def _discover_subnets(self, region: str) -> list[ParsedResource]:
        ec2 = self._session(region).client("ec2")
        result = []
        for sub in ec2.describe_subnets().get("Subnets", []):
            tags = _tags_dict(sub.get("Tags", []))
            result.append(_parsed(
                "aws_subnet", sub["SubnetId"], tags.get("Name", sub["SubnetId"]),
                {"cidr_block": sub.get("CidrBlock"), "vpc_id": sub.get("VpcId"),
                 "availability_zone": sub.get("AvailabilityZone"), "id": sub["SubnetId"], "tags": tags}, region,
            ))
        return result

    def _discover_security_groups(self, region: str) -> list[ParsedResource]:
        ec2 = self._session(region).client("ec2")
        result = []
        for sg in ec2.describe_security_groups().get("SecurityGroups", []):
            tags = _tags_dict(sg.get("Tags", []))
            result.append(_parsed(
                "aws_security_group", sg["GroupId"], sg.get("GroupName", sg["GroupId"]),
                {"description": sg.get("Description"), "vpc_id": sg.get("VpcId"),
                 "ingress": sg.get("IpPermissions", []), "id": sg["GroupId"], "tags": tags}, region,
            ))
        return result

    def _discover_instances(self, region: str) -> list[ParsedResource]:
        ec2 = self._session(region).client("ec2")
        result = []
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    tags = _tags_dict(inst.get("Tags", []))
                    result.append(_parsed(
                        "aws_instance", inst["InstanceId"], tags.get("Name", inst["InstanceId"]),
                        {"instance_type": inst.get("InstanceType"),
                         "availability_zone": inst.get("Placement", {}).get("AvailabilityZone"),
                         "subnet_id": inst.get("SubnetId"),
                         "vpc_security_group_ids": [sg["GroupId"] for sg in inst.get("SecurityGroups", [])],
                         "id": inst["InstanceId"], "tags": tags}, region,
                    ))
        return result

    def _discover_s3_buckets(self, region: str) -> list[ParsedResource]:
        """S3 is global — only discover from the first region to avoid duplicates."""
        if region != self.regions[0]:
            return []
        s3 = self._session(region).client("s3")
        result = []
        for bucket in s3.list_buckets().get("Buckets", []):
            try:
                loc = s3.get_bucket_location(Bucket=bucket["Name"])
                bucket_region = loc.get("LocationConstraint") or "us-east-1"
                tags_raw = s3.get_bucket_tagging(Bucket=bucket["Name"]).get("TagSet", [])
                tags = _tags_dict(tags_raw)
            except Exception:
                bucket_region = region
                tags = {}
            result.append(_parsed(
                "aws_s3_bucket", bucket["Name"], bucket["Name"],
                {"id": bucket["Name"], "region": bucket_region, "tags": tags}, "global",
            ))
        return result

    def _discover_rds_instances(self, region: str) -> list[ParsedResource]:
        rds = self._session(region).client("rds")
        result = []
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                result.append(_parsed(
                    "aws_db_instance", db["DBInstanceIdentifier"], db["DBInstanceIdentifier"],
                    {"engine": db.get("Engine"), "engine_version": db.get("EngineVersion"),
                     "instance_class": db.get("DBInstanceClass"),
                     "allocated_storage": db.get("AllocatedStorage"),
                     "id": db["DBInstanceIdentifier"]}, region,
                ))
        return result

    def _discover_iam_roles(self, region: str) -> list[ParsedResource]:
        """IAM is global — only from first region."""
        if region != self.regions[0]:
            return []
        iam = self._session(region).client("iam")
        result = []
        paginator = iam.get_paginator("list_roles")
        for page in paginator.paginate():
            for role in page.get("Roles", []):
                result.append(_parsed(
                    "aws_iam_role", role["RoleId"], role["RoleName"],
                    {"name": role["RoleName"], "arn": role.get("Arn"),
                     "assume_role_policy": role.get("AssumeRolePolicyDocument"), "id": role["RoleId"]}, "global",
                ))
        return result

    def _discover_lambda_functions(self, region: str) -> list[ParsedResource]:
        lmb = self._session(region).client("lambda")
        result = []
        paginator = lmb.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page.get("Functions", []):
                result.append(_parsed(
                    "aws_lambda_function", fn["FunctionArn"], fn["FunctionName"],
                    {"runtime": fn.get("Runtime"), "handler": fn.get("Handler"),
                     "memory_size": fn.get("MemorySize"), "id": fn["FunctionName"]}, region,
                ))
        return result

    def _discover_eks_clusters(self, region: str) -> list[ParsedResource]:
        eks = self._session(region).client("eks")
        result = []
        for name in eks.list_clusters().get("clusters", []):
            try:
                cluster = eks.describe_cluster(name=name)["cluster"]
                result.append(_parsed(
                    "aws_eks_cluster", cluster["arn"], name,
                    {"version": cluster.get("version"), "status": cluster.get("status"), "id": name}, region,
                ))
            except Exception:
                pass
        return result

    def _discover_load_balancers(self, region: str) -> list[ParsedResource]:
        elb = self._session(region).client("elbv2")
        result = []
        paginator = elb.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for lb in page.get("LoadBalancers", []):
                result.append(_parsed(
                    "aws_lb", lb["LoadBalancerArn"], lb["LoadBalancerName"],
                    {"type": lb.get("Type"), "scheme": lb.get("Scheme"), "id": lb["LoadBalancerArn"]}, region,
                ))
        return result

    def _discover_sns_topics(self, region: str) -> list[ParsedResource]:
        sns = self._session(region).client("sns")
        result = []
        paginator = sns.get_paginator("list_topics")
        for page in paginator.paginate():
            for topic in page.get("Topics", []):
                arn = topic["TopicArn"]
                name = arn.split(":")[-1]
                result.append(_parsed("aws_sns_topic", arn, name, {"arn": arn, "id": arn}, region))
        return result

    def _discover_sqs_queues(self, region: str) -> list[ParsedResource]:
        sqs = self._session(region).client("sqs")
        result = []
        for url in sqs.list_queues().get("QueueUrls", []):
            name = url.split("/")[-1]
            result.append(_parsed("aws_sqs_queue", url, name, {"url": url, "id": url}, region))
        return result

    def _discover_cloudwatch_alarms(self, region: str) -> list[ParsedResource]:
        cw = self._session(region).client("cloudwatch")
        result = []
        paginator = cw.get_paginator("describe_alarms")
        for page in paginator.paginate():
            for alarm in page.get("MetricAlarms", []):
                result.append(_parsed(
                    "aws_cloudwatch_metric_alarm", alarm["AlarmArn"], alarm["AlarmName"],
                    {"state": alarm.get("StateValue"), "id": alarm["AlarmName"]}, region,
                ))
        return result

    def _discover_route53_zones(self, region: str) -> list[ParsedResource]:
        """Route53 is global — only from first region."""
        if region != self.regions[0]:
            return []
        r53 = self._session(region).client("route53")
        result = []
        for zone in r53.list_hosted_zones().get("HostedZones", []):
            result.append(_parsed(
                "aws_route53_zone", zone["Id"], zone["Name"],
                {"name": zone["Name"], "private": zone.get("Config", {}).get("PrivateZone"), "id": zone["Id"]}, "global",
            ))
        return result

    def _simulate(self) -> list[AWSDiscoveryResult]:
        """Return realistic simulation data without AWS credentials."""
        from migration_factory.discovery.providers.cloud import AWSDiscovery
        sim = AWSDiscovery(simulation=True)
        result = sim.discover(regions=self.regions)
        parsed = sim.to_parsed_resources(result)
        return [AWSDiscoveryResult(
            region=self.regions[0], resources=parsed,
            resource_counts={r.source_type: 1 for r in parsed}, mode="simulation",
        )]
