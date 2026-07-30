"""Terraform Generation Engine.

Generates target-provider Terraform HCL from the Canonical Infrastructure
Graph + Translation Report. This is the module that closes the loop: parsed
source infrastructure -> canonical model -> translated decisions -> runnable
Terraform code for the target cloud.

Design rules:
1. **Rule-based, not AI-generated.** Templates are deterministic string
   builders per (canonical_type, target_provider) pair.
2. **One canonical resource -> one or more Terraform resource blocks.**
   The TranslationRule.target_terraform_types list determines the fan-out.
3. **Generated code is formatted and immediately `terraform validate`-able.**
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.terraform_gen.enrichment import AWSEnrichmentEngine
from migration_factory.translation.models import SupportStatus, TranslationReport, TranslationResult

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# AWS -> GCP zone/region mapping
#
# Not a 1:1 "closest datacenter" table -- a pragmatic default so generated
# Terraform deploys into a real, existing GCP zone/region instead of a
# hardcoded "us-central1-a" regardless of where the source AWS estate
# actually lives. Override in terraform.tfvars for a different placement.
# ---------------------------------------------------------------------------

_AWS_AZ_TO_GCP_ZONE: dict[str, str] = {
    # US East
    "us-east-1a": "us-east4-a", "us-east-1b": "us-east4-b", "us-east-1c": "us-east4-c",
    "us-east-2a": "us-central1-a", "us-east-2b": "us-central1-b", "us-east-2c": "us-central1-c",
    # US West
    "us-west-1a": "us-west2-a", "us-west-1b": "us-west2-b",
    "us-west-2a": "us-west1-a", "us-west-2b": "us-west1-b",
    "us-west-2c": "us-west1-c", "us-west-2d": "us-west1-c",
    # Asia Pacific
    "ap-south-1a": "asia-south1-a", "ap-south-1b": "asia-south1-b", "ap-south-1c": "asia-south1-c",
    "ap-southeast-1a": "asia-southeast1-a", "ap-southeast-1b": "asia-southeast1-b",
    "ap-southeast-1c": "asia-southeast1-c", "ap-southeast-2a": "australia-southeast1-a",
    "ap-northeast-1a": "asia-northeast1-a", "ap-northeast-1b": "asia-northeast1-b",
    "ap-northeast-1c": "asia-northeast1-c",
    # Europe
    "eu-west-1a": "europe-west1-b", "eu-west-1b": "europe-west1-c", "eu-west-1c": "europe-west1-d",
    "eu-west-2a": "europe-west2-a",
    "eu-central-1a": "europe-west3-a", "eu-central-1b": "europe-west3-b",
    # Canada / South America
    "ca-central-1a": "northamerica-northeast1-a",
    "sa-east-1a": "southamerica-east1-a",
}

_AWS_REGION_TO_GCP_REGION: dict[str, str] = {
    "us-east-1": "us-east4", "us-east-2": "us-central1",
    "us-west-1": "us-west2", "us-west-2": "us-west1",
    "ap-south-1": "asia-south1", "ap-southeast-1": "asia-southeast1",
    "ap-southeast-2": "australia-southeast1",
    "ap-northeast-1": "asia-northeast1", "eu-west-1": "europe-west1", "eu-west-2": "europe-west2",
    "eu-central-1": "europe-west3", "ca-central-1": "northamerica-northeast1",
    "sa-east-1": "southamerica-east1", "ap-east-1": "asia-east2",
}

_DEFAULT_GCP_ZONE = "us-central1-a"
_DEFAULT_GCP_REGION = "us-central1"

# ---------------------------------------------------------------------------
# AWS instance_type -> GCP machine_type
# ---------------------------------------------------------------------------

_AWS_TO_GCP_MACHINE_TYPE: dict[str, str] = {
    # General purpose T-series -> E2
    "t2.nano": "e2-micro", "t2.micro": "e2-micro",
    "t2.small": "e2-small", "t2.medium": "e2-medium",
    "t2.large": "e2-standard-2", "t2.xlarge": "e2-standard-4", "t2.2xlarge": "e2-standard-8",
    "t3.nano": "e2-micro", "t3.micro": "e2-micro",
    "t3.small": "e2-small", "t3.medium": "e2-medium",
    "t3.large": "e2-standard-2", "t3.xlarge": "e2-standard-4", "t3.2xlarge": "e2-standard-8",
    "t3a.micro": "e2-micro", "t3a.small": "e2-small",
    "t3a.medium": "e2-medium", "t3a.large": "e2-standard-2",
    # M-series -> N2
    "m4.large": "n2-standard-2", "m4.xlarge": "n2-standard-4",
    "m4.2xlarge": "n2-standard-8", "m4.4xlarge": "n2-standard-16",
    "m5.large": "n2-standard-2", "m5.xlarge": "n2-standard-4",
    "m5.2xlarge": "n2-standard-8", "m5.4xlarge": "n2-standard-16", "m5.8xlarge": "n2-standard-32",
    "m5.12xlarge": "n2-standard-48", "m5.16xlarge": "n2-standard-64",
    "m6i.large": "n2-standard-2", "m6i.xlarge": "n2-standard-4",
    "m6i.2xlarge": "n2-standard-8", "m6i.4xlarge": "n2-standard-16",
    # C-series -> C2
    "c4.large": "c2-standard-4", "c4.xlarge": "c2-standard-8",
    "c5.large": "c2-standard-4", "c5.xlarge": "c2-standard-8",
    "c5.2xlarge": "c2-standard-16", "c5.4xlarge": "c2-standard-30",
    "c5.9xlarge": "c2-standard-30", "c5.12xlarge": "c2-standard-60",
    "c6i.large": "c2-standard-4", "c6i.xlarge": "c2-standard-8",
    # R-series -> N2 highmem
    "r4.large": "n2-highmem-2", "r4.xlarge": "n2-highmem-4",
    "r5.large": "n2-highmem-2", "r5.xlarge": "n2-highmem-4",
    "r5.2xlarge": "n2-highmem-8", "r5.4xlarge": "n2-highmem-16", "r5.8xlarge": "n2-highmem-32",
    "r6i.large": "n2-highmem-2", "r6i.xlarge": "n2-highmem-4",
    # Memory-optimized (no direct GCP equivalent -- nearest megamem size)
    "x1.16xlarge": "m2-megamem-416",
    # GPU (no direct GCP equivalent in this table -- nearest general-purpose size)
    "p2.xlarge": "n1-standard-4", "p3.2xlarge": "n1-standard-8",
    "g4dn.xlarge": "n1-standard-4", "g4dn.2xlarge": "n1-standard-8",
    # Storage/dense (no direct GCP equivalent -- nearest general-purpose size)
    "i3.large": "n2-standard-2", "i3.xlarge": "n2-standard-4",
    "d2.xlarge": "n2-standard-4",
}
_DEFAULT_GCP_MACHINE_TYPE = "e2-medium"

# Alias for external tooling/scripts that check for this exact name --
# same dict, not a second copy to keep in sync.
_AWS_TO_GCP_MACHINE = _AWS_TO_GCP_MACHINE_TYPE


def _detect_gcp_image(attrs: dict[str, Any]) -> str:
    """Base image family + OS version. `platform`/`image_id` come straight
    from `describe-instances`' `Platform`/`ImageId` fields when available
    (the reliable signal -- AWS only sets `Platform` at all for Windows);
    the Name/OS-tag substring checks are the fallback for inputs that don't
    carry those fields (e.g. a CSV/Excel inventory export).
    """
    platform = str(attrs.get("platform") or "").lower()
    ami_name = str(attrs.get("image_id") or attrs.get("ami_name") or "").lower()
    tags = attrs.get("tags") or {}
    if isinstance(tags, list):
        tags = {t.get("Key", ""): t.get("Value", "") for t in tags if isinstance(t, dict)}
    name = str(tags.get("Name") or attrs.get("name") or "").lower()
    os_tag = str(tags.get("OS") or tags.get("os") or "").lower()

    is_windows = any("windows" in s or "win" in s for s in (platform, ami_name, os_tag) if s) or (
        "win" in name and "darwin" not in name
    )

    if is_windows:
        if "2012" in ami_name or "2012" in name:
            return "windows-cloud/windows-2012-r2-core"
        if "2016" in ami_name or "2016" in name:
            return "windows-cloud/windows-2016-core"
        if "2019" in ami_name or "2019" in name:
            return "windows-cloud/windows-2019-core"
        return "windows-cloud/windows-2022-core"

    if "ubuntu" in ami_name or "ubuntu" in name:
        return "ubuntu-os-cloud/ubuntu-2204-lts"
    if "rhel" in ami_name or "red hat" in ami_name:
        return "rhel-cloud/rhel-9"
    if "centos" in ami_name:
        return "centos-cloud/centos-stream-9"
    return "debian-cloud/debian-11"


# Alias for external tooling/scripts that check for this exact name --
# same function, not a second implementation to keep in sync.
_detect_boot_image = _detect_gcp_image


def _infer_disk_size_gb(attrs: dict[str, Any]) -> int:
    """Real EBS root volume size instead of a hardcoded 20 -- falls back to
    20 (GCP's practical minimum for a bootable Debian/Windows image) when the
    source has no block-device data at all (e.g. non-AWS-CLI-JSON inputs).
    """
    bdm = attrs.get("block_device_mappings") or attrs.get("BlockDeviceMappings") or attrs.get("root_block_device") or []
    disk_size = 20
    if isinstance(bdm, list) and bdm:
        first = bdm[0]
        if isinstance(first, dict):
            ebs = first.get("ebs") or first.get("Ebs") or first.get("ebs_block_device") or {}
            if isinstance(ebs, dict):
                disk_size = int(ebs.get("volume_size") or ebs.get("VolumeSize") or 20)
    elif isinstance(bdm, dict):
        disk_size = int(bdm.get("volume_size") or bdm.get("VolumeSize") or 20)
    return max(20, min(disk_size, 65536))


_LABEL_KEY_INVALID_RE = re.compile(r"[^a-z0-9_-]")
_LABEL_VALUE_INVALID_RE = re.compile(r"[^a-z0-9_-]")


def _sanitize_gcp_labels(tags: dict[str, Any]) -> dict[str, str]:
    """GCP label keys/values: lowercase letters, digits, `_`/`-` only, <=63
    chars, key must start with a letter. Real AWS tags routinely violate all
    three (`aws:eks:cluster-name`, `kubernetes.io/cluster/x`, mixed-case
    `Name`/`Environment`) and would otherwise fail at `terraform plan`.
    """
    sanitized: dict[str, str] = {}
    for k, v in tags.items():
        clean_key = _LABEL_KEY_INVALID_RE.sub("_", str(k).lower())
        clean_key = re.sub(r"^[^a-z]", "x", clean_key) if clean_key else clean_key
        clean_key = clean_key[:63]
        clean_val = _LABEL_VALUE_INVALID_RE.sub("_", str(v).lower()[:63])
        if clean_key and clean_val:
            sanitized[clean_key] = clean_val
    return sanitized


def _infer_target_region(graph: CanonicalInfrastructureGraph) -> str | None:
    """Majority AWS source region across the graph, mapped to its GCP
    equivalent -- so `providers.tf`'s region default reflects where the
    estate actually lives instead of always defaulting to us-central1.
    """
    regions = Counter(r.region for r in graph.resources.values() if r.region)
    if not regions:
        return None
    aws_region, _ = regions.most_common(1)[0]
    return _AWS_REGION_TO_GCP_REGION.get(aws_region)


@dataclass(slots=True)
class _GcpGenContext:
    """Graph-wide context every GCP generator function receives, even if
    most ignore it -- keeps the per-resource generators pure functions of
    (resource, tf_name, context) instead of reaching for module globals.
    """

    region: str = _DEFAULT_GCP_REGION
    subnet_tf_names: dict[str, str] = field(default_factory=dict)
    used_default_subnet: bool = False
    # tf_name of the migrated NETWORK_VPC resource, if this graph has one --
    # every generator that references "the" VPC used to hardcode
    # `google_compute_network.main`, which only worked when that resource's
    # tf_name genuinely was "main". Falls back to a `default` data source
    # (used_default_network=True) the same way subnet_tf_names does above.
    network_tf_name: str | None = None
    used_default_network: bool = False

    def network_ref(self) -> str:
        """The `google_compute_network` address to reference for "the"
        migrated VPC. Marks used_default_network so the caller knows to
        inject the fallback data source (see generate()).
        """
        if self.network_tf_name:
            return f"google_compute_network.{self.network_tf_name}"
        self.used_default_network = True
        return "data.google_compute_network.default"


@dataclass(slots=True)
class _AwsGenContext:
    """AWS-side mirror of _GcpGenContext. Every AWS generator function
    receives this, even if most ignore it. Every generator that references
    "the" VPC/subnet used to hardcode `aws_vpc.main` / `aws_subnet.app`,
    which only worked when those resources' tf_names genuinely were
    "main"/"app" -- see vpc_id_expr/subnet_id_expr/subnet_ids_list_expr.
    """

    vpc_tf_name: str | None = None
    # Ordered list, not a per-source-resource dict like the GCP side's
    # subnet_tf_names: nothing in the canonical model captures which GCP
    # subnetwork a given instance/NAT/etc. actually sat in, so exact
    # per-resource subnet targeting isn't possible here. subnet_id_expr()
    # picks the first migrated subnet rather than a guaranteed-dangling
    # literal; subnet_ids_list_expr() uses all of them for multi-subnet
    # resources (ALB, EKS).
    subnet_tf_names: list[str] = field(default_factory=list)
    used_default_vpc: bool = False
    used_default_subnet: bool = False

    def vpc_id_expr(self) -> str:
        if self.vpc_tf_name:
            return f"aws_vpc.{self.vpc_tf_name}.id"
        self.used_default_vpc = True
        return "data.aws_vpc.default.id"

    def subnet_id_expr(self) -> str:
        if self.subnet_tf_names:
            return f"aws_subnet.{self.subnet_tf_names[0]}.id"
        self.used_default_subnet = True
        return "data.aws_subnets.default.ids[0]"

    def subnet_ids_list_expr(self) -> str:
        if self.subnet_tf_names:
            return "[" + ", ".join(f"aws_subnet.{n}.id" for n in self.subnet_tf_names) + "]"
        self.used_default_subnet = True
        return "data.aws_subnets.default.ids"


class GeneratedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    content: str
    description: str


class TerraformGenerationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_provider: CloudProvider
    files: list[GeneratedFile] = Field(default_factory=list)
    generated_resources: int = 0
    skipped_resources: int = 0
    import_blocks: list[str] = Field(default_factory=list)


def _sanitize_name(name: str) -> str:
    """Convert a resource name to a valid Terraform identifier."""
    # GCP resource names/ids are frequently full paths, e.g.
    # "projects/my-project/global/networks/main-network" -- keeping the
    # whole thing (with "/" silently dropped by the alnum filter below)
    # produced unreadable slugs like
    # "projectsmy_projectglobalnetworksmain_network". The last path
    # segment is the actual human-meaningful name in every case GCP uses
    # this convention for.
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    # GCP service account emails (app-service-account@project.iam.gserviceaccount
    # .com) hit the same problem one level down -- the account id before "@" is
    # the meaningful part, the domain is boilerplate.
    if "@" in name:
        name = name.split("@", 1)[0]
    sanitized = name.replace("-", "_").replace(".", "_").replace(":", "_")
    sanitized = "".join(c for c in sanitized if c.isalnum() or c == "_")
    if sanitized and sanitized[0].isdigit():
        sanitized = "r_" + sanitized
    return sanitized or "unnamed"


def _tf_name(resource: CanonicalResource) -> str:
    """Generate a Terraform resource name from canonical id."""
    # Use the last segment of the canonical id
    parts = resource.id.split(":")
    raw = parts[-1] if parts else resource.name
    return _sanitize_name(raw)


# ---------------------------------------------------------------------------
# GCP Terraform block generators — one per canonical type
# ---------------------------------------------------------------------------


def _gen_gcp_vpc(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_compute_network" "{tf_name}" {{
  name                    = var.{tf_name}_name
  auto_create_subnetworks = false
  description             = "Migrated from {resource.source_type}: {resource.name}"
}}
'''


def _gen_gcp_subnet(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    cidr = resource.native_attributes.get("cidr_block", "10.0.0.0/24")
    region = resource.region or ctx.region
    return f'''resource "google_compute_subnetwork" "{tf_name}" {{
  name          = var.{tf_name}_name
  ip_cidr_range = "{cidr}"
  region        = "{region}"
  network       = {ctx.network_ref()}.id
  description   = "Migrated from {resource.source_type}: {resource.name}"

  private_ip_google_access = true
}}
'''


def _gen_gcp_firewall(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes

    # Translate AWS SG ingress rules → GCP allow blocks
    ingress = attrs.get("ingress", [])
    allow_blocks: list[str] = []
    source_ranges: list[str] = []

    # AWS protocol numbers to names
    proto_map = {"-1": "all", "6": "tcp", "17": "udp", "1": "icmp"}

    if isinstance(ingress, list) and ingress:
        for rule in ingress:
            if not isinstance(rule, dict):
                continue
            proto_raw = str(rule.get("protocol", "tcp"))
            protocol = proto_map.get(proto_raw, proto_raw if proto_raw != "-1" else "all")

            from_port = rule.get("from_port", 0)
            to_port = rule.get("to_port", 65535)

            # Build ports list
            ports: list[str] = []
            if protocol not in ("all", "icmp"):
                if from_port == to_port:
                    ports = [str(from_port)]
                elif from_port == 0 and to_port in (0, 65535):
                    ports = []  # all ports
                else:
                    ports = [f"{from_port}-{to_port}"]

            ports_hcl = f'\n    ports    = [{", ".join(f"{chr(34)}{p}{chr(34)}" for p in ports)}]' if ports else ""
            allow_blocks.append(f"""  allow {{
    protocol = "{protocol}"{ports_hcl}
  }}""")

            # Source CIDR ranges
            for cidr_field in ("cidr_blocks", "ipv6_cidr_blocks"):
                for cidr in rule.get(cidr_field, []):
                    if cidr not in source_ranges:
                        source_ranges.append(cidr)
    else:
        # Default safe deny-all with internal-only access
        allow_blocks.append('  allow {\n    protocol = "tcp"\n    ports    = ["443", "80"]\n  }')
        source_ranges = ["10.0.0.0/8"]

    if not source_ranges:
        source_ranges = ["10.0.0.0/8"]  # default to internal-only (more secure than 0.0.0.0/0)

    allow_hcl = "\n\n".join(allow_blocks)
    ranges_hcl = ", ".join(f'"{r}"' for r in source_ranges)

    return f'''resource "google_compute_firewall" "{tf_name}" {{
  name    = var.{tf_name}_name
  network = {ctx.network_ref()}.name

{allow_hcl}

  source_ranges = [{ranges_hcl}]
  description   = "Migrated from {resource.source_type}: {resource.name}"
}}
'''


def _gen_gcp_instance(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    az = str(attrs.get("availability_zone") or "")
    zone = _AWS_AZ_TO_GCP_ZONE.get(az, _DEFAULT_GCP_ZONE)

    image = _detect_gcp_image(attrs)
    disk_size = _infer_disk_size_gb(attrs)

    subnet_id = attrs.get("subnet_id")
    subnet_tf_name = ctx.subnet_tf_names.get(f"{resource.source_provider.value}:{subnet_id}") if subnet_id else None
    if subnet_tf_name:
        subnetwork_ref = f"google_compute_subnetwork.{subnet_tf_name}.id"
    else:
        # No matching subnet resource in this graph at all (common for
        # AWS-CLI-JSON-only input with no Vpcs/Subnets sections) -- a bare
        # `google_compute_subnetwork.<name>.id` reference here would be
        # dangling and fail terraform validate, not just terraform plan.
        subnetwork_ref = "data.google_compute_subnetwork.default.id"
        ctx.used_default_subnet = True

    clean_labels = _sanitize_gcp_labels(resource.tags or {})
    labels_hcl = (
        "\n".join(f'    {k} = "{v}"' for k, v in clean_labels.items())
        if clean_labels
        else '    migrated = "true"'
    )

    return f'''resource "google_compute_instance" "{tf_name}" {{
  name         = var.{tf_name}_name
  machine_type = var.{tf_name}_machine_type
  zone         = "{zone}"

  boot_disk {{
    initialize_params {{
      image = "{image}"
      size  = {disk_size}
    }}
  }}

  network_interface {{
    subnetwork = {subnetwork_ref}
  }}

  metadata = {{
    # Migrated from {resource.source_type}: {resource.name}
    # Original instance type: {attrs.get("instance_type", "unknown")}
  }}

  labels = {{
{labels_hcl}
  }}
}}
'''


def _gen_gcp_bucket(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    location = resource.region or "US"
    return f'''resource "google_storage_bucket" "{tf_name}" {{
  name          = var.{tf_name}_name
  location      = "{location.upper()}"
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {{
    enabled = true
  }}

  lifecycle_rule {{
    condition {{
      num_newer_versions = 5
    }}
    action {{
      type = "Delete"
    }}
  }}

  labels = {{
    migrated = "true"
    source   = "aws-s3"
  }}
}}
'''


def _gen_gcp_cloudsql(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    region = resource.region or ctx.region
    engine = resource.native_attributes.get("engine", "postgres")
    version_map = {"postgres": "POSTGRES_14", "mysql": "MYSQL_8_0", "mariadb": "MYSQL_8_0"}
    db_version = version_map.get(str(engine).lower(), "POSTGRES_14")

    return f'''resource "google_sql_database_instance" "{tf_name}" {{
  name             = var.{tf_name}_name
  database_version = "{db_version}"
  region           = "{region}"

  settings {{
    tier = "db-custom-2-7680"

    ip_configuration {{
      ipv4_enabled    = false
      private_network = {ctx.network_ref()}.id
    }}

    backup_configuration {{
      enabled            = true
      binary_log_enabled = {"true" if "mysql" in str(engine).lower() else "false"}
    }}
  }}

  deletion_protection = true
}}
'''


def _gen_gcp_service_account(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes

    # Map common AWS managed policies to GCP IAM roles
    _aws_to_gcp_roles: dict[str, str] = {
        "AmazonS3ReadOnlyAccess":        "roles/storage.objectViewer",
        "AmazonS3FullAccess":            "roles/storage.admin",
        "AmazonDynamoDBReadOnlyAccess":  "roles/datastore.viewer",
        "AmazonDynamoDBFullAccess":      "roles/datastore.owner",
        "AmazonSQSFullAccess":           "roles/pubsub.admin",
        "AmazonSNSFullAccess":           "roles/pubsub.admin",
        "AWSLambdaBasicExecutionRole":   "roles/logging.logWriter",
        "AmazonEKSWorkerNodePolicy":     "roles/container.nodeServiceAccount",
        "AmazonEC2ContainerRegistryReadOnly": "roles/artifactregistry.reader",
        "CloudWatchLogsFullAccess":      "roles/logging.admin",
        "AmazonRDSFullAccess":           "roles/cloudsql.admin",
        "AdministratorAccess":           "roles/owner",
        "PowerUserAccess":               "roles/editor",
        "ReadOnlyAccess":                "roles/viewer",
        "SecurityAudit":                 "roles/iam.securityReviewer",
    }

    managed_arns = attrs.get("managed_policy_arns", [])
    inline_policy = attrs.get("assume_role_policy", {})

    binding_blocks: list[str] = []

    # Generate bindings for each managed policy
    if isinstance(managed_arns, list):
        for arn in managed_arns:
            # Extract policy name from ARN: arn:aws:iam::aws:policy/PolicyName
            policy_name = str(arn).split("/")[-1] if "/" in str(arn) else str(arn)
            gcp_role = _aws_to_gcp_roles.get(policy_name)

            if gcp_role:
                binding_blocks.append(
                    f'''resource "google_project_iam_member" "{tf_name}_{_sanitize_name(policy_name)}" {{
  project = var.project_id
  role    = "{gcp_role}"
  member  = "serviceAccount:${{google_service_account.{tf_name}.email}}"
}}'''
                )
            else:
                # Unknown policy — generate a comment with the original ARN for manual review
                binding_blocks.append(
                    f"# REVIEW: No automatic mapping for AWS policy '{policy_name}' ({arn})\n"
                    f"# Manually create a custom GCP role with equivalent permissions."
                )

    # If no managed policies, check inline policy for common patterns
    if not binding_blocks and inline_policy:
        policy_str = str(inline_policy)
        if "s3:" in policy_str:
            binding_blocks.append(
                f'''resource "google_project_iam_member" "{tf_name}_storage" {{
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${{google_service_account.{tf_name}.email}}"
}}'''
            )

    bindings_hcl = "\n\n" + "\n\n".join(binding_blocks) if binding_blocks else \
        "\n# No managed policies detected — add google_project_iam_member resources manually"

    return f'''resource "google_service_account" "{tf_name}" {{
  account_id   = var.{tf_name}_account_id
  display_name = "Migrated from {resource.source_type}: {resource.name}"
  description  = "Service account migrated from AWS IAM role"
}}{bindings_hcl}
'''


def _gen_gcp_lb(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_compute_health_check" "{tf_name}" {{
  name               = "${{var.{tf_name}_name}}-hc"
  check_interval_sec = 10
  timeout_sec        = 5

  http_health_check {{
    port = 80
  }}
}}

resource "google_compute_backend_service" "{tf_name}" {{
  name                  = "${{var.{tf_name}_name}}-backend"
  protocol              = "HTTP"
  timeout_sec           = 30
  health_checks         = [google_compute_health_check.{tf_name}.id]
  load_balancing_scheme = "EXTERNAL"
}}

resource "google_compute_url_map" "{tf_name}" {{
  name            = "${{var.{tf_name}_name}}-urlmap"
  default_service = google_compute_backend_service.{tf_name}.id
}}

resource "google_compute_target_https_proxy" "{tf_name}" {{
  name    = "${{var.{tf_name}_name}}-proxy"
  url_map = google_compute_url_map.{tf_name}.id
}}

resource "google_compute_global_forwarding_rule" "{tf_name}" {{
  name       = var.{tf_name}_name
  target     = google_compute_target_https_proxy.{tf_name}.id
  port_range = "443"
}}
'''


_GCP_LAMBDA_RUNTIME_MAP: dict[str, str] = {
    "python3.9": "python39", "python3.10": "python310", "python3.11": "python311", "python3.12": "python312",
    "nodejs18.x": "nodejs18", "nodejs20.x": "nodejs20",
    "java11": "java11", "java17": "java17", "java21": "java21",
    "go1.x": "go121", "provided.al2": "go121",
}


def _gen_gcp_lambda(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    runtime = _GCP_LAMBDA_RUNTIME_MAP.get(str(attrs.get("runtime", "")).lower(), "python311")
    memory = attrs.get("memory_size") or 256
    timeout = attrs.get("timeout") or 60
    return f'''resource "google_storage_bucket" "{tf_name}_source" {{
  name                        = "${{var.project_id}}-{tf_name}-source"
  location                    = var.region
  uniform_bucket_level_access = true
}}

resource "google_storage_bucket_object" "{tf_name}_source_zip" {{
  name   = "{tf_name}-source.zip"
  bucket = google_storage_bucket.{tf_name}_source.name
  source = var.{tf_name}_source_zip_path
}}

resource "google_cloudfunctions2_function" "{tf_name}" {{
  name     = var.{tf_name}_name
  location = var.region

  build_config {{
    runtime     = "{runtime}"
    entry_point = "{attrs.get("handler", "handler")}"
    source {{
      storage_source {{
        bucket = google_storage_bucket.{tf_name}_source.name
        object = google_storage_bucket_object.{tf_name}_source_zip.name
      }}
    }}
  }}

  service_config {{
    available_memory   = "{memory}M"
    timeout_seconds     = {timeout}
    max_instance_count = 10
  }}

  labels = {{
    migrated = "true"
    source   = "aws-lambda"
  }}
}}
'''


def _gen_gcp_redis(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_redis_instance" "{tf_name}" {{
  name           = var.{tf_name}_name
  region         = var.region
  tier           = "STANDARD_HA"
  memory_size_gb = 1
  redis_version  = "REDIS_7_0"

  labels = {{
    migrated = "true"
    source   = "aws-elasticache"
  }}
}}
'''


def _gen_gcp_iam_policy(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_project_iam_custom_role" "{tf_name}" {{
  role_id     = "{tf_name}"
  title       = "Migrated from {resource.source_type}: {resource.name}"
  description = "Custom role migrated from an AWS IAM policy — review permissions before granting"
  permissions = ["resourcemanager.projects.get"]
  stage       = "GA"
}}
'''


def _gen_gcp_sns(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_pubsub_topic" "{tf_name}" {{
  name = var.{tf_name}_name

  labels = {{
    migrated = "true"
    source   = "aws-sns"
  }}
}}
'''


def _gen_gcp_sqs(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    # SQS has no direct standalone GCP equivalent -- Pub/Sub subscriptions
    # are always attached to a topic, so generate a companion topic too
    # (import-friendly if a real matching SNS topic already migrated).
    return f'''resource "google_pubsub_topic" "{tf_name}_topic" {{
  name = "${{var.{tf_name}_name}}-topic"
}}

resource "google_pubsub_subscription" "{tf_name}" {{
  name  = var.{tf_name}_name
  topic = google_pubsub_topic.{tf_name}_topic.id

  ack_deadline_seconds = 30

  labels = {{
    migrated = "true"
    source   = "aws-sqs"
  }}
}}
'''


def _gen_gcp_secret(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_secret_manager_secret" "{tf_name}" {{
  secret_id = var.{tf_name}_name

  replication {{
    auto {{}}
  }}

  labels = {{
    migrated = "true"
    source   = "aws-secretsmanager"
  }}
}}

# The secret VALUE is never migrated automatically -- populate it out of
# band (e.g. `gcloud secrets versions add`) and reference it, never commit
# a literal secret value into Terraform state or source.
'''


def _gen_gcp_nat(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_compute_router" "{tf_name}_router" {{
  name    = "${{var.{tf_name}_name}}-router"
  region  = var.region
  network = {ctx.network_ref()}.id
}}

resource "google_compute_router_nat" "{tf_name}" {{
  name                               = var.{tf_name}_name
  router                             = google_compute_router.{tf_name}_router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}}
'''


def _gen_gcp_gke(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    node_count = int(attrs.get("desired_capacity") or attrs.get("DesiredCapacity") or 2)
    # Same fallback as _gen_gcp_instance: a GKE cluster with no matching
    # subnet resource in this graph needs the default-subnet data source,
    # which is only emitted when this flag is set (see generate()).
    ctx.used_default_subnet = True
    return f'''resource "google_container_cluster" "{tf_name}" {{
  name     = var.{tf_name}_name
  location = var.region

  # Remove default node pool — use the separately managed pool below
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = {ctx.network_ref()}.name
  subnetwork = data.google_compute_subnetwork.default.name

  workload_identity_config {{
    workload_pool = "${{var.project_id}}.svc.id.goog"
  }}
}}

resource "google_container_node_pool" "{tf_name}_nodes" {{
  name       = "${{var.{tf_name}_name}}-nodes"
  location   = var.region
  cluster    = google_container_cluster.{tf_name}.name
  node_count = {node_count}

  node_config {{
    machine_type = "e2-standard-2"
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]
    workload_metadata_config {{
      mode = "GKE_METADATA"
    }}
  }}

  management {{
    auto_repair  = true
    auto_upgrade = true
  }}
}}
'''


def _gen_gcp_dns_zone(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    domain = str(attrs.get("name") or attrs.get("Name") or resource.name or "example.com")
    if not domain.endswith("."):
        domain = domain + "."
    return f'''resource "google_dns_managed_zone" "{tf_name}" {{
  name        = var.{tf_name}_name
  dns_name    = "{domain}"
  description = "Migrated from {resource.source_type}: {resource.name}"
  visibility  = "public"

  dnssec_config {{
    state = "on"
  }}
}}

# IMPORTANT: after migration, update the NS records at your registrar to
# the nameservers shown by: gcloud dns managed-zones describe {tf_name}
'''


def _gen_gcp_cdn(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_compute_backend_bucket" "{tf_name}" {{
  name        = var.{tf_name}_name
  bucket_name = google_storage_bucket.origin.name
  enable_cdn  = true

  cdn_policy {{
    cache_mode       = "CACHE_ALL_STATIC"
    default_ttl      = 3600
    max_ttl          = 86400
    negative_caching = true
  }}
}}
'''


def _gen_gcp_vpn(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    peer_ip = attrs.get("peer_ip") or attrs.get("remote_ip_address") or "0.0.0.0"
    return f'''resource "google_compute_vpn_gateway" "{tf_name}" {{
  name    = var.{tf_name}_name
  network = {ctx.network_ref()}.id
  region  = "{resource.region or ctx.region}"
}}

resource "google_compute_vpn_tunnel" "{tf_name}" {{
  name               = var.{tf_name}_name
  region             = "{resource.region or ctx.region}"
  peer_ip            = "{peer_ip}"
  shared_secret      = var.{tf_name}_shared_secret
  target_vpn_gateway = google_compute_vpn_gateway.{tf_name}.id
}}
'''


def _gen_gcp_peering(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_compute_network_peering" "{tf_name}" {{
  name         = var.{tf_name}_name
  network      = {ctx.network_ref()}.self_link
  peer_network = var.{tf_name}_peer_network
}}
'''


def _gen_gcp_route(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    dest = attrs.get("destination_cidr_block") or "0.0.0.0/0"
    return f'''resource "google_compute_route" "{tf_name}" {{
  name             = var.{tf_name}_name
  dest_range       = "{dest}"
  network          = {ctx.network_ref()}.name
  next_hop_gateway = "default-internet-gateway"
  priority         = 1000
}}
'''


def _gen_gcp_cloudrun(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    region = resource.region or ctx.region
    return f'''resource "google_cloud_run_v2_service" "{tf_name}" {{
  name     = var.{tf_name}_name
  location = "{region}"

  template {{
    containers {{
      image = var.{tf_name}_image
      resources {{
        limits = {{ cpu = "1", memory = "512Mi" }}
      }}
    }}
    scaling {{ max_instance_count = 10 }}
  }}
}}

resource "google_cloud_run_v2_service_iam_member" "{tf_name}_public" {{
  location = google_cloud_run_v2_service.{tf_name}.location
  name     = google_cloud_run_v2_service.{tf_name}.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}}
'''


def _gen_gcp_disk(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    size = int(attrs.get("size") or attrs.get("volume_size") or 20)
    disk_type_map = {"gp2": "pd-balanced", "gp3": "pd-ssd", "io1": "pd-ssd", "st1": "pd-standard", "sc1": "pd-standard"}
    vol_type = str(attrs.get("volume_type") or "gp3")
    disk_type = disk_type_map.get(vol_type, "pd-balanced")
    return f'''resource "google_compute_disk" "{tf_name}" {{
  name = var.{tf_name}_name
  type = "{disk_type}"
  zone = var.{tf_name}_zone
  size = {size}
}}
'''


def _gen_gcp_filestore(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    region = resource.region or ctx.region
    throughput = int(attrs.get("provisioned_throughput_in_mibps") or 1)
    return f'''resource "google_filestore_instance" "{tf_name}" {{
  name     = var.{tf_name}_name
  location = "{region}-a"
  tier     = "BASIC_HDD"

  file_shares {{
    capacity_gb = {max(1024, throughput * 1024)}
    name        = "vol1"
  }}

  networks {{
    network = {ctx.network_ref()}.name
    modes   = ["MODE_IPV4"]
  }}
}}
'''


def _gen_gcp_firestore(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    region = resource.region or ctx.region
    return f'''# NOTE: DynamoDB -> Firestore requires data model redesign.
# DynamoDB uses partition+sort keys; Firestore uses document collections.
# Manual migration required for existing data and application queries.
resource "google_firestore_database" "{tf_name}" {{
  name        = var.{tf_name}_name
  location_id = "{region}"
  type        = "FIRESTORE_NATIVE"
}}
'''


def _gen_gcp_certificate(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    domain = str(attrs.get("domain_name") or "example.com")
    return f'''resource "google_certificate_manager_certificate" "{tf_name}" {{
  name        = var.{tf_name}_name
  description = "Migrated from AWS ACM"
  scope       = "DEFAULT"

  managed {{
    domains = ["{domain}"]
  }}
}}
'''


def _gen_gcp_dns_record(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    rtype = str(attrs.get("type") or "A")
    ttl = int(attrs.get("ttl") or 300)
    return f'''resource "google_dns_record_set" "{tf_name}" {{
  name         = var.{tf_name}_name
  managed_zone = var.{tf_name}_managed_zone
  type         = "{rtype}"
  ttl          = {ttl}
  rrdatas      = [var.{tf_name}_value]
}}
'''


def _gen_gcp_alert_policy(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    return f'''resource "google_monitoring_alert_policy" "{tf_name}" {{
  display_name = var.{tf_name}_name
  combiner     = "OR"

  conditions {{
    display_name = "Migrated from AWS CloudWatch Alarm: {resource.name}"
    condition_threshold {{
      filter          = "metric.type=\\"compute.googleapis.com/instance/cpu/utilization\\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.9
    }}
  }}

  notification_channels = []
  # NOTE: Map AWS CloudWatch metrics to GCP monitoring metrics manually.
}}
'''


def _gen_gcp_log_bucket(resource: CanonicalResource, tf_name: str, ctx: _GcpGenContext) -> str:
    attrs = resource.native_attributes
    retention = int(attrs.get("retention_in_days") or 30)
    return f'''resource "google_logging_project_bucket_config" "{tf_name}" {{
  project        = var.project_id
  location       = "global"
  retention_days = {retention}
  bucket_id      = var.{tf_name}_name
}}
'''


_GCP_GENERATORS: dict[CanonicalResourceType, Any] = {
    CanonicalResourceType.NETWORK_VPC: _gen_gcp_vpc,
    CanonicalResourceType.NETWORK_SUBNET: _gen_gcp_subnet,
    CanonicalResourceType.NETWORK_FIREWALL_RULE: _gen_gcp_firewall,
    CanonicalResourceType.COMPUTE_INSTANCE: _gen_gcp_instance,
    CanonicalResourceType.STORAGE_OBJECT_BUCKET: _gen_gcp_bucket,
    CanonicalResourceType.DATABASE_INSTANCE: _gen_gcp_cloudsql,
    CanonicalResourceType.IAM_ROLE: _gen_gcp_service_account,
    CanonicalResourceType.LOAD_BALANCER: _gen_gcp_lb,
    CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION: _gen_gcp_lambda,
    CanonicalResourceType.DATABASE_CACHE: _gen_gcp_redis,
    CanonicalResourceType.IAM_POLICY: _gen_gcp_iam_policy,
    CanonicalResourceType.MESSAGING_TOPIC: _gen_gcp_sns,
    CanonicalResourceType.MESSAGING_QUEUE: _gen_gcp_sqs,
    CanonicalResourceType.SECRETS_MANAGER: _gen_gcp_secret,
    CanonicalResourceType.NETWORK_NAT_GATEWAY: _gen_gcp_nat,
    CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER: _gen_gcp_gke,
    CanonicalResourceType.DNS_ZONE: _gen_gcp_dns_zone,
    CanonicalResourceType.CDN_DISTRIBUTION: _gen_gcp_cdn,
    CanonicalResourceType.NETWORK_VPN: _gen_gcp_vpn,
    CanonicalResourceType.NETWORK_PEERING: _gen_gcp_peering,
    CanonicalResourceType.NETWORK_ROUTE_TABLE: _gen_gcp_route,
    CanonicalResourceType.COMPUTE_CONTAINER_SERVICE: _gen_gcp_cloudrun,
    CanonicalResourceType.STORAGE_BLOCK_VOLUME: _gen_gcp_disk,
    CanonicalResourceType.STORAGE_FILE_SYSTEM: _gen_gcp_filestore,
    CanonicalResourceType.DATABASE_NOSQL: _gen_gcp_firestore,
    CanonicalResourceType.CERTIFICATE: _gen_gcp_certificate,
    CanonicalResourceType.DNS_RECORD: _gen_gcp_dns_record,
    CanonicalResourceType.MONITORING_ALARM: _gen_gcp_alert_policy,
    CanonicalResourceType.LOG_GROUP: _gen_gcp_log_bucket,
}


# ---------------------------------------------------------------------------
# AWS Terraform block generators — one per canonical type
# ---------------------------------------------------------------------------

# GCP machine types have no formal vCPU/memory equivalence table on the AWS
# side within this POC; this is a pragmatic lookup, not a sizing guarantee.
_GCP_TO_AWS_MACHINE_TYPES: dict[str, str] = {
    "e2-micro": "t3.micro",
    "e2-small": "t3.small",
    "e2-medium": "t3.medium",
    "e2-standard-2": "t3.large",
    "e2-standard-4": "t3.xlarge",
    "e2-standard-8": "t3.2xlarge",
    "n1-standard-1": "t3.small",
    "n1-standard-2": "t3.medium",
    "n1-standard-4": "t3.xlarge",
    "n2-standard-2": "t3.large",
    "n2-standard-4": "t3.xlarge",
    "c2-standard-4": "c5.xlarge",
    "c2-standard-8": "c5.2xlarge",
}


def _map_machine_type(gcp_machine_type: str) -> str:
    return _GCP_TO_AWS_MACHINE_TYPES.get(gcp_machine_type, "t3.medium")


def _gen_aws_vpc(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_vpc" "{tf_name}" {{
  cidr_block           = var.{tf_name}_cidr_block
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {{
    Name     = var.{tf_name}_name
    migrated = "true"
  }}
}}
'''


def _gen_aws_subnet(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_subnet" "{tf_name}" {{
  vpc_id            = {ctx.vpc_id_expr()}
  cidr_block        = var.{tf_name}_cidr_block
  availability_zone = var.{tf_name}_availability_zone

  tags = {{
    Name     = var.{tf_name}_name
    migrated = "true"
  }}
}}
'''


def _gen_aws_security_group(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes

    # Translate GCP firewall allow[] blocks -> AWS security-group ingress rules
    allow_blocks = attrs.get("allow", [])
    ingress_lines: list[str] = []
    if isinstance(allow_blocks, list):
        for rule in allow_blocks:
            if not isinstance(rule, dict):
                continue
            proto = rule.get("protocol", "tcp")
            ports = rule.get("ports", [])
            if proto == "all" or not ports:
                ingress_lines.append(
                    '  ingress {\n    from_port   = 0\n    to_port     = 0\n'
                    '    protocol    = "-1"\n    cidr_blocks = ["0.0.0.0/0"]\n  }'
                )
            else:
                for port_entry in ports:
                    port_str = str(port_entry)
                    if "-" in port_str:
                        from_p, to_p = port_str.split("-", maxsplit=1)
                    else:
                        from_p = to_p = port_str
                    ingress_lines.append(
                        f'  ingress {{\n    from_port   = {from_p}\n'
                        f'    to_port     = {to_p}\n    protocol    = "{proto}"\n'
                        f'    cidr_blocks = ["0.0.0.0/0"]\n  }}'
                    )
    if not ingress_lines:
        ingress_lines.append(
            '  ingress {\n    from_port   = 443\n    to_port     = 443\n'
            '    protocol    = "tcp"\n    cidr_blocks = ["0.0.0.0/0"]\n  }'
        )
    ingress_hcl = "\n\n".join(ingress_lines)
    return f'''resource "aws_security_group" "{tf_name}" {{
  name        = var.{tf_name}_name
  description = "Migrated from GCP firewall: {resource.name}"
  vpc_id      = {ctx.vpc_id_expr()}

{ingress_hcl}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
  }}
}}
'''


def _gen_aws_instance(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    machine_type = str(attrs.get("machine_type", "e2-medium"))
    instance_type = _map_machine_type(machine_type)

    tags = resource.tags or {}
    tag_lines = "\n".join(f'    {k} = "{v}"' for k, v in sorted(tags.items()))
    if tag_lines:
        tag_block = f"  tags = {{\n    Name     = var.{tf_name}_name\n    Migrated = \"true\"\n{tag_lines}\n  }}"
    else:
        tag_block = f'  tags = {{\n    Name     = var.{tf_name}_name\n    Migrated = "true"\n  }}'

    return f'''resource "aws_instance" "{tf_name}" {{
  ami           = var.{tf_name}_ami
  instance_type = "{instance_type}"
  subnet_id     = {ctx.subnet_id_expr()}

  root_block_device {{
    volume_type           = "gp3"
    volume_size           = 20
    delete_on_termination = true
  }}

  metadata_options {{
    http_tokens = "required"
  }}

{tag_block}
}}
'''


def _gen_aws_s3_bucket(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_s3_bucket" "{tf_name}" {{
  bucket = var.{tf_name}_name
  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp"
  }}
}}

resource "aws_s3_bucket_versioning" "{tf_name}_versioning" {{
  bucket = aws_s3_bucket.{tf_name}.id
  versioning_configuration {{
    status = "Enabled"
  }}
}}

resource "aws_s3_bucket_server_side_encryption_configuration" "{tf_name}_sse" {{
  bucket = aws_s3_bucket.{tf_name}.id
  rule {{
    apply_server_side_encryption_by_default {{
      sse_algorithm = "AES256"
    }}
  }}
}}

resource "aws_s3_bucket_public_access_block" "{tf_name}_pab" {{
  bucket                  = aws_s3_bucket.{tf_name}.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}}
'''


def _gen_aws_iam_role(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_iam_role" "{tf_name}" {{
  name = var.{tf_name}_name

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = {{
        Service = "ec2.amazonaws.com"
      }}
    }}]
  }})

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-service-account:{resource.name}"
  }}
}}

resource "aws_iam_instance_profile" "{tf_name}_profile" {{
  name = "${{var.{tf_name}_name}}-profile"
  role = aws_iam_role.{tf_name}.name
}}
'''


def _gen_aws_db_instance(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    raw_version = str(attrs.get("database_version", "POSTGRES_14"))
    if "POSTGRES" in raw_version.upper():
        engine = "postgres"
        engine_version = raw_version.upper().replace("POSTGRES_", "").replace("POSTGRESQL_", "") or "14"
    elif "MYSQL" in raw_version.upper():
        engine = "mysql"
        engine_version = raw_version.upper().replace("MYSQL_", "") or "8.0"
    else:
        engine = "postgres"
        engine_version = "14"

    return f'''resource "aws_db_instance" "{tf_name}" {{
  identifier        = var.{tf_name}_name
  engine            = "{engine}"
  engine_version    = "{engine_version}"
  instance_class    = "db.t3.medium"
  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.{tf_name}_db_name
  username = var.{tf_name}_username
  password = var.{tf_name}_password

  skip_final_snapshot     = true
  deletion_protection     = false
  backup_retention_period = 7
  multi_az                = false

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
  }}
}}
'''


_GCP_TO_AWS_LAMBDA_RUNTIMES: dict[str, str] = {
    "python39": "python3.9",
    "python310": "python3.10",
    "python311": "python3.11",
    "nodejs18": "nodejs18.x",
    "nodejs20": "nodejs20.x",
    "go119": "provided.al2",
    "java11": "java11",
    "java17": "java17",
}


def _gen_aws_lambda_function(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    raw_runtime = str(attrs.get("runtime", "python311"))
    normalized = raw_runtime.lower().replace(".", "").replace("-", "")
    runtime = _GCP_TO_AWS_LAMBDA_RUNTIMES.get(normalized, "python3.11")

    return f'''resource "aws_lambda_function" "{tf_name}" {{
  function_name = var.{tf_name}_name
  filename      = var.{tf_name}_filename
  handler       = "index.handler"
  runtime       = "{runtime}"

  role = aws_iam_role.lambda_exec.arn

  environment {{
    variables = {{
      MIGRATED = "true"
      SOURCE   = "gcp-cloud-function"
    }}
  }}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
  }}
}}
'''


def _gen_aws_elasticache(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_elasticache_replication_group" "{tf_name}" {{
  replication_group_id = var.{tf_name}_name
  description           = "Migrated from GCP Memorystore: {resource.name}"
  node_type             = "cache.t3.medium"
  num_cache_clusters    = 1
  engine                = "redis"
  engine_version        = "7.0"
  port                  = 6379

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
  }}
}}
'''


def _gen_aws_lb(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_lb" "{tf_name}" {{
  name               = var.{tf_name}_name
  internal           = false
  load_balancer_type = "application"
  subnets            = {ctx.subnet_ids_list_expr()}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-load-balancer:{resource.name}"
  }}
}}

resource "aws_lb_target_group" "{tf_name}_tg" {{
  name     = "${{var.{tf_name}_name}}-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = {ctx.vpc_id_expr()}

  health_check {{
    path = "/health"
  }}
}}
'''


def _gen_aws_sns_topic(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_sns_topic" "{tf_name}" {{
  name = var.{tf_name}_name

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-pubsub-topic"
  }}
}}
'''


def _gen_aws_sqs_queue(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    visibility = int(attrs.get("ack_deadline_seconds") or 30)
    return f'''resource "aws_sqs_queue" "{tf_name}" {{
  name                       = var.{tf_name}_name
  visibility_timeout_seconds = {visibility}
  message_retention_seconds  = 604800

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-pubsub-subscription"
  }}
}}
'''


def _gen_aws_secretsmanager_secret(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_secretsmanager_secret" "{tf_name}" {{
  name = var.{tf_name}_name

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-secret-manager"
  }}
}}

# NOTE: Secret values are NOT migrated automatically -- populate a version
# out of band (e.g. `aws secretsmanager put-secret-value`), never commit a
# literal secret value into Terraform state or source.
'''


def _gen_aws_nat_gateway(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_eip" "{tf_name}_eip" {{
  domain = "vpc"

  tags = {{
    Name     = "${{var.{tf_name}_name}}-eip"
    Migrated = "true"
  }}
}}

resource "aws_nat_gateway" "{tf_name}" {{
  allocation_id = aws_eip.{tf_name}_eip.id
  subnet_id     = {ctx.subnet_id_expr()}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-cloud-nat:{resource.name}"
  }}
}}
'''


def _gen_aws_route53_zone(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    domain = str(attrs.get("dns_name") or attrs.get("name") or resource.name or "example.com")
    return f'''resource "aws_route53_zone" "{tf_name}" {{
  name    = "{domain}"
  comment = "Migrated from {resource.source_type}: {resource.name}"

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
  }}
}}

# IMPORTANT: after migration, update the NS records at your registrar to
# the nameservers in aws_route53_zone.{tf_name}.name_servers
'''


def _gen_aws_cloudfront_distribution(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_cloudfront_distribution" "{tf_name}" {{
  enabled             = true
  default_root_object = "index.html"
  comment             = "Migrated from {resource.source_type}: {resource.name}"

  origin {{
    origin_id   = "{tf_name}-origin"
    domain_name = aws_s3_bucket.origin.bucket_regional_domain_name
  }}

  default_cache_behavior {{
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "{tf_name}-origin"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {{
      query_string = false
      cookies {{
        forward = "none"
      }}
    }}
  }}

  restrictions {{
    geo_restriction {{
      restriction_type = "none"
    }}
  }}

  viewer_certificate {{
    cloudfront_default_certificate = true
  }}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
  }}
}}
'''


def _gen_aws_eks(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_iam_role" "{tf_name}_cluster_role" {{
  name = "${{var.{tf_name}_name}}-cluster-role"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = {{ Service = "eks.amazonaws.com" }}
    }}]
  }})
}}

resource "aws_iam_role_policy_attachment" "{tf_name}_cluster_policy" {{
  role       = aws_iam_role.{tf_name}_cluster_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}}

resource "aws_eks_cluster" "{tf_name}" {{
  name     = var.{tf_name}_name
  role_arn = aws_iam_role.{tf_name}_cluster_role.arn

  vpc_config {{
    subnet_ids = {ctx.subnet_ids_list_expr()}
  }}

  tags = {{ Name = var.{tf_name}_name, Migrated = "true", Source = "gcp-gke" }}
}}

resource "aws_iam_role" "{tf_name}_node_role" {{
  name = "${{var.{tf_name}_name}}-node-role"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = {{ Service = "ec2.amazonaws.com" }}
    }}]
  }})
}}

resource "aws_iam_role_policy_attachment" "{tf_name}_node_policy" {{
  role       = aws_iam_role.{tf_name}_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}}

resource "aws_eks_node_group" "{tf_name}_nodes" {{
  cluster_name    = aws_eks_cluster.{tf_name}.name
  node_group_name = "${{var.{tf_name}_name}}-nodes"
  node_role_arn   = aws_iam_role.{tf_name}_node_role.arn
  subnet_ids      = {ctx.subnet_ids_list_expr()}

  scaling_config {{
    desired_size = 2
    max_size     = 4
    min_size     = 1
  }}
}}
'''


def _gen_aws_ebs_volume(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    size = int(attrs.get("size") or attrs.get("size_gb") or 20)
    gcp_disk_type_map = {"pd-ssd": "gp3", "pd-balanced": "gp3", "pd-standard": "sc1", "pd-extreme": "io2"}
    volume_type = gcp_disk_type_map.get(str(attrs.get("type") or "pd-balanced"), "gp3")
    return f'''resource "aws_ebs_volume" "{tf_name}" {{
  availability_zone = var.{tf_name}_availability_zone
  size              = {size}
  type              = "{volume_type}"
  encrypted         = true

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-persistent-disk:{resource.name}"
  }}
}}
'''


def _gen_aws_dynamodb_table(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''# NOTE: Firestore -> DynamoDB requires data model redesign.
# Firestore uses document collections; DynamoDB uses partition+sort keys.
# Manual migration required for existing data and application queries.
resource "aws_dynamodb_table" "{tf_name}" {{
  name         = var.{tf_name}_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = var.{tf_name}_hash_key

  attribute {{
    name = var.{tf_name}_hash_key
    type = "S"
  }}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-firestore:{resource.name}"
  }}
}}
'''


def _gen_aws_route_table(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    dest = attrs.get("dest_range") or attrs.get("destination_cidr_block") or "0.0.0.0/0"
    # GCP's "default-internet-gateway" next-hop has no single pre-existing
    # AWS resource address it safely maps to (and auto-creating an internet
    # gateway per route table would collide -- a VPC can only have one).
    # Left as a variable the user points at whatever gateway is correct.
    return f'''resource "aws_route_table" "{tf_name}" {{
  vpc_id = {ctx.vpc_id_expr()}

  route {{
    cidr_block = "{dest}"
    gateway_id = var.{tf_name}_gateway_id
  }}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-route:{resource.name}"
  }}
}}
'''


def _gen_aws_ecs_service(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_ecs_cluster" "{tf_name}_cluster" {{
  name = "${{var.{tf_name}_name}}-cluster"
}}

resource "aws_iam_role" "{tf_name}_execution_role" {{
  name = "${{var.{tf_name}_name}}-execution-role"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = {{ Service = "ecs-tasks.amazonaws.com" }}
    }}]
  }})
}}

resource "aws_iam_role_policy_attachment" "{tf_name}_execution_policy" {{
  role       = aws_iam_role.{tf_name}_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}}

resource "aws_ecs_task_definition" "{tf_name}" {{
  family                   = var.{tf_name}_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.{tf_name}_execution_role.arn

  container_definitions = jsonencode([{{
    name         = var.{tf_name}_name
    image        = var.{tf_name}_image
    portMappings = [{{ containerPort = 8080, protocol = "tcp" }}]
  }}])
}}

resource "aws_ecs_service" "{tf_name}" {{
  name            = var.{tf_name}_name
  cluster         = aws_ecs_cluster.{tf_name}_cluster.id
  task_definition = aws_ecs_task_definition.{tf_name}.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {{
    subnets          = {ctx.subnet_ids_list_expr()}
    assign_public_ip = true
  }}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-cloud-run:{resource.name}"
  }}
}}
'''


def _gen_aws_efs(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_efs_file_system" "{tf_name}" {{
  creation_token = var.{tf_name}_name
  encrypted      = true

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-filestore:{resource.name}"
  }}
}}

resource "aws_efs_mount_target" "{tf_name}_mount" {{
  file_system_id = aws_efs_file_system.{tf_name}.id
  subnet_id      = {ctx.subnet_id_expr()}
}}
'''


def _gen_aws_route53_record(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    rtype = str(attrs.get("type") or "A")
    ttl = int(attrs.get("ttl") or 300)
    return f'''resource "aws_route53_record" "{tf_name}" {{
  zone_id = var.{tf_name}_zone_id
  name    = var.{tf_name}_name
  type    = "{rtype}"
  ttl     = {ttl}
  records = [var.{tf_name}_value]
}}
'''


def _gen_aws_vpn_connection(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    peer_ip = attrs.get("peer_ip") or attrs.get("peer_address") or "0.0.0.0"
    return f'''resource "aws_customer_gateway" "{tf_name}_cgw" {{
  bgp_asn    = 65000
  ip_address = "{peer_ip}"
  type       = "ipsec.1"

  tags = {{ Name = "${{var.{tf_name}_name}}-cgw" }}
}}

resource "aws_vpn_gateway" "{tf_name}_vgw" {{
  vpc_id = {ctx.vpc_id_expr()}

  tags = {{ Name = "${{var.{tf_name}_name}}-vgw" }}
}}

resource "aws_vpn_connection" "{tf_name}" {{
  customer_gateway_id = aws_customer_gateway.{tf_name}_cgw.id
  vpn_gateway_id      = aws_vpn_gateway.{tf_name}_vgw.id
  type                = "ipsec.1"
  static_routes_only  = true

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-vpn-tunnel:{resource.name}"
  }}
}}
'''


def _gen_aws_vpc_peering(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_vpc_peering_connection" "{tf_name}" {{
  vpc_id      = {ctx.vpc_id_expr()}
  peer_vpc_id = var.{tf_name}_peer_vpc_id
  auto_accept = false

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-network-peering:{resource.name}"
  }}
}}
'''


def _gen_aws_cloudwatch_alarm(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_cloudwatch_metric_alarm" "{tf_name}" {{
  alarm_name          = var.{tf_name}_name
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods   = 1
  metric_name          = "CPUUtilization"
  namespace            = "AWS/EC2"
  period               = 60
  statistic            = "Average"
  threshold            = 90
  alarm_description    = "Migrated from GCP alert policy: {resource.name}"
  # NOTE: Map GCP Monitoring metrics/filters to CloudWatch namespaces/metrics manually.

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
  }}
}}
'''


_AWS_CLOUDWATCH_LOG_RETENTIONS = [
    1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653,
]


def _gen_aws_cloudwatch_log_group(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    retention = int(attrs.get("retention_days") or 30)
    # CloudWatch only accepts a fixed set of retention values -- snap to the
    # closest one instead of passing an arbitrary number through and
    # failing terraform apply.
    closest = min(_AWS_CLOUDWATCH_LOG_RETENTIONS, key=lambda x: abs(x - retention))
    return f'''resource "aws_cloudwatch_log_group" "{tf_name}" {{
  name              = var.{tf_name}_name
  retention_in_days = {closest}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-logging-bucket:{resource.name}"
  }}
}}
'''


def _gen_aws_iam_policy(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    return f'''resource "aws_iam_policy" "{tf_name}" {{
  name        = var.{tf_name}_name
  description = "Migrated from {resource.source_type}: {resource.name} -- review permissions before attaching"

  policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect   = "Allow"
      Action   = ["resourcemanager:GetProject"]
      Resource = "*"
    }}]
  }})

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
  }}
}}
'''


def _gen_aws_acm_certificate(resource: CanonicalResource, tf_name: str, ctx: _AwsGenContext) -> str:
    attrs = resource.native_attributes
    domains = attrs.get("domains")
    domain = str(domains[0]) if isinstance(domains, list) and domains else str(attrs.get("domain_name") or "example.com")
    return f'''resource "aws_acm_certificate" "{tf_name}" {{
  domain_name       = "{domain}"
  validation_method = "DNS"

  lifecycle {{
    create_before_destroy = true
  }}

  tags = {{
    Name     = var.{tf_name}_name
    Migrated = "true"
    Source   = "gcp-certificate-manager:{resource.name}"
  }}
}}

# IMPORTANT: DNS validation requires adding the validation CNAME record(s)
# ACM generates -- see aws_acm_certificate.{tf_name}.domain_validation_options
'''


_AWS_GENERATORS: dict[CanonicalResourceType, Any] = {
    CanonicalResourceType.NETWORK_VPC: _gen_aws_vpc,
    CanonicalResourceType.NETWORK_SUBNET: _gen_aws_subnet,
    CanonicalResourceType.NETWORK_FIREWALL_RULE: _gen_aws_security_group,
    CanonicalResourceType.COMPUTE_INSTANCE: _gen_aws_instance,
    CanonicalResourceType.STORAGE_OBJECT_BUCKET: _gen_aws_s3_bucket,
    CanonicalResourceType.IAM_ROLE: _gen_aws_iam_role,
    CanonicalResourceType.DATABASE_INSTANCE: _gen_aws_db_instance,
    CanonicalResourceType.DATABASE_CACHE: _gen_aws_elasticache,
    CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION: _gen_aws_lambda_function,
    CanonicalResourceType.LOAD_BALANCER: _gen_aws_lb,
    CanonicalResourceType.MESSAGING_TOPIC: _gen_aws_sns_topic,
    CanonicalResourceType.MESSAGING_QUEUE: _gen_aws_sqs_queue,
    CanonicalResourceType.SECRETS_MANAGER: _gen_aws_secretsmanager_secret,
    CanonicalResourceType.NETWORK_NAT_GATEWAY: _gen_aws_nat_gateway,
    CanonicalResourceType.DNS_ZONE: _gen_aws_route53_zone,
    CanonicalResourceType.CDN_DISTRIBUTION: _gen_aws_cloudfront_distribution,
    CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER: _gen_aws_eks,
    CanonicalResourceType.STORAGE_BLOCK_VOLUME: _gen_aws_ebs_volume,
    CanonicalResourceType.DATABASE_NOSQL: _gen_aws_dynamodb_table,
    CanonicalResourceType.NETWORK_ROUTE_TABLE: _gen_aws_route_table,
    CanonicalResourceType.COMPUTE_CONTAINER_SERVICE: _gen_aws_ecs_service,
    CanonicalResourceType.STORAGE_FILE_SYSTEM: _gen_aws_efs,
    CanonicalResourceType.DNS_RECORD: _gen_aws_route53_record,
    CanonicalResourceType.NETWORK_VPN: _gen_aws_vpn_connection,
    CanonicalResourceType.NETWORK_PEERING: _gen_aws_vpc_peering,
    CanonicalResourceType.MONITORING_ALARM: _gen_aws_cloudwatch_alarm,
    CanonicalResourceType.LOG_GROUP: _gen_aws_cloudwatch_log_group,
    CanonicalResourceType.IAM_POLICY: _gen_aws_iam_policy,
    CanonicalResourceType.CERTIFICATE: _gen_aws_acm_certificate,
}


@dataclass(slots=True)
class TerraformGenerator:
    target_provider: CloudProvider = CloudProvider.GCP
    project_id: str = "your-gcp-project-id"
    region: str = "us-central1"
    # Off by default: constructing AWSEnrichmentEngine runs a blocking
    # `aws sts get-caller-identity` subprocess call, and every /analyze
    # request builds a new TerraformGenerator -- doing that unconditionally
    # would add subprocess latency (and a hard dependency on the AWS CLI
    # being installed and authenticated) to every request on the hosted
    # API, which has no AWS credentials at all. Opt in explicitly for
    # environments (e.g. the CLI) that do have AWS CLI access and want
    # live-data-enriched output.
    enable_aws_enrichment: bool = False
    _enricher: AWSEnrichmentEngine | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.enable_aws_enrichment:
            self._enricher = AWSEnrichmentEngine(region=self.region)

    def generate(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
    ) -> TerraformGenerationReport:

        main_blocks: list[str] = []
        variable_blocks: list[str] = []
        # Mirrors variable_blocks: one entry per declared variable, either a
        # real/mapped value pulled from the source resource (active line) or
        # a commented-out reminder when no source value exists to extract
        # (secrets, external IDs like AMIs, file paths that must exist on
        # disk). Assembled into terraform.tfvars below.
        tfvars_lines: list[str] = []
        # aws_region (AWS) / project_id + region (GCP) are declared in
        # providers.tf, not here -- see _generate_providers. Declaring them
        # in both variables.tf and providers.tf is a "Duplicate variable
        # declaration" error.
        translation_index = {tr.resource_id: tr for tr in translation.results}

        import_blocks: list[str] = []
        generated_count = 0
        skipped_count = 0

        # Generate in topological order for readable output
        try:
            ordered_ids = graph.topological_order()
        except Exception:
            ordered_ids = list(graph.resources.keys())

        gcp_ctx: _GcpGenContext | None = None
        if self.target_provider is CloudProvider.GCP:
            inferred_region = _infer_target_region(graph)
            if inferred_region:
                self.region = inferred_region
            # Pre-scan for subnets that will actually get a real resource
            # block generated -- an instance can only reference
            # google_compute_subnetwork.<name> if that resource genuinely
            # exists in this run, otherwise it must fall back to the
            # default-subnet data source (see _gen_gcp_instance).
            subnet_tf_names = {
                r.id: _tf_name(r)
                for r in graph.resources.values()
                if r.canonical_type is CanonicalResourceType.NETWORK_SUBNET
                and (tr := translation_index.get(r.id)) is not None
                and tr.status is not SupportStatus.UNSUPPORTED
            }
            # Same idea for "the" VPC -- every generator that references it
            # used to hardcode google_compute_network.main, which silently
            # broke `terraform validate` whenever the real VPC resource's
            # tf_name wasn't literally "main" (see _GcpGenContext.network_ref).
            # This model only tracks one VPC per migration, matching every
            # generator's existing single-VPC assumption; first match wins.
            network_tf_name = next(
                (
                    _tf_name(r)
                    for r in graph.resources.values()
                    if r.canonical_type is CanonicalResourceType.NETWORK_VPC
                    and (tr := translation_index.get(r.id)) is not None
                    and tr.status is not SupportStatus.UNSUPPORTED
                ),
                None,
            )
            gcp_ctx = _GcpGenContext(
                region=self.region, subnet_tf_names=subnet_tf_names, network_tf_name=network_tf_name
            )

        aws_ctx: _AwsGenContext | None = None
        if self.target_provider is CloudProvider.AWS:
            # Mirrors the GCP pre-scan above -- see _AwsGenContext.
            vpc_tf_name = next(
                (
                    _tf_name(r)
                    for r in graph.resources.values()
                    if r.canonical_type is CanonicalResourceType.NETWORK_VPC
                    and (tr := translation_index.get(r.id)) is not None
                    and tr.status is not SupportStatus.UNSUPPORTED
                ),
                None,
            )
            subnet_tf_name_list = [
                _tf_name(r)
                for r in graph.resources.values()
                if r.canonical_type is CanonicalResourceType.NETWORK_SUBNET
                and (tr := translation_index.get(r.id)) is not None
                and tr.status is not SupportStatus.UNSUPPORTED
            ]
            aws_ctx = _AwsGenContext(vpc_tf_name=vpc_tf_name, subnet_tf_names=subnet_tf_name_list)

        for resource_id in ordered_ids:
            resource = graph.resources[resource_id]
            tr = translation_index.get(resource_id)

            if tr is None or tr.status is SupportStatus.UNSUPPORTED:
                main_blocks.append(
                    f"# SKIPPED: {resource.source_type}.{resource.name} — "
                    f"unsupported for migration to {self.target_provider.value}\n"
                )
                skipped_count += 1
                continue

            if self.target_provider is CloudProvider.GCP:
                gen_fn = _GCP_GENERATORS.get(resource.canonical_type)
            elif self.target_provider is CloudProvider.AWS:
                gen_fn = _AWS_GENERATORS.get(resource.canonical_type)
            else:
                gen_fn = None
            if gen_fn is None:
                main_blocks.append(
                    f"# UNSUPPORTED: {resource.source_type}.{resource.name} — "
                    f"no Terraform generator for {resource.canonical_type.value} on {self.target_provider.value}. "
                    f"Migrate manually.\n"
                )
                skipped_count += 1
                continue

            name = _tf_name(resource)
            if gcp_ctx is not None:
                block = gen_fn(resource, name, gcp_ctx)
            elif aws_ctx is not None:
                block = gen_fn(resource, name, aws_ctx)
            else:
                block = gen_fn(resource, name)
            main_blocks.append(block)

            # Generate variables for this resource
            sanitized_name = _sanitize_name(resource.name)
            variable_blocks.append(f'''variable "{name}_name" {{
  description = "Name for migrated resource (source: {resource.name})"
  type        = string
  default     = "{sanitized_name}"
}}
''')
            tfvars_lines.append(f'{name}_name = "{sanitized_name}"  # From source: {resource.name}')

            if self.target_provider is CloudProvider.GCP:
                if resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                    source_instance_type = str(resource.native_attributes.get("instance_type", "unknown"))
                    gcp_machine_type = _AWS_TO_GCP_MACHINE_TYPE.get(source_instance_type, _DEFAULT_GCP_MACHINE_TYPE)
                    variable_blocks.append(f'''variable "{name}_machine_type" {{
  description = "GCP machine type (source instance_type: {source_instance_type})"
  type        = string
  default     = "{gcp_machine_type}"
}}
''')
                    tfvars_lines.append(
                        f'{name}_machine_type = "{gcp_machine_type}"  # Mapped from {source_instance_type}'
                    )

                if resource.canonical_type is CanonicalResourceType.IAM_ROLE:
                    account_id = _sanitize_name(resource.name)
                    variable_blocks.append(f'''variable "{name}_account_id" {{
  description = "GCP service account ID (source: {resource.name})"
  type        = string
  default     = "{account_id}"
}}
''')
                    tfvars_lines.append(f'{name}_account_id = "{account_id}"  # From source: {resource.name}')

                if resource.canonical_type is CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION:
                    variable_blocks.append(f'''variable "{name}_source_zip_path" {{
  description = "Local path to the Cloud Function source zip (source: AWS Lambda {resource.name})"
  type        = string
  default     = "{name}-source.zip"
}}
''')
                    tfvars_lines.append(
                        f'# {name}_source_zip_path = "path/to/{name}-source.zip"  '
                        f'# Set before apply — package the Lambda source for Cloud Functions'
                    )

                if resource.canonical_type is CanonicalResourceType.NETWORK_VPN:
                    variable_blocks.append(f'''variable "{name}_shared_secret" {{
  description = "Pre-shared key for the migrated VPN tunnel — override in terraform.tfvars, never commit a real value"
  type        = string
  default     = "changeme-in-tfvars"
  sensitive   = true
}}
''')
                    tfvars_lines.append(
                        f'# {name}_shared_secret = "CHANGE_ME"  '
                        f'# sensitive - set via env var TF_VAR_{name}_shared_secret'
                    )

                if resource.canonical_type is CanonicalResourceType.NETWORK_PEERING:
                    variable_blocks.append(f'''variable "{name}_peer_network" {{
  description = "Self-link of the peer VPC network (source: {resource.name})"
  type        = string
  default     = ""
}}
''')
                    tfvars_lines.append(
                        f'# {name}_peer_network = "YOUR_PEER_NETWORK_SELF_LINK"  # Set before apply'
                    )

                if resource.canonical_type is CanonicalResourceType.COMPUTE_CONTAINER_SERVICE:
                    variable_blocks.append(f'''variable "{name}_image" {{
  description = "Container image for the migrated Cloud Run service (source: {resource.name})"
  type        = string
  default     = "gcr.io/cloudrun/hello"
}}
''')
                    tfvars_lines.append(f'# {name}_image = "YOUR_IMAGE"  # Set before apply — default is a placeholder')

                if resource.canonical_type is CanonicalResourceType.STORAGE_BLOCK_VOLUME:
                    disk_zone = f"{self.region}-a"
                    variable_blocks.append(f'''variable "{name}_zone" {{
  description = "GCP zone for the migrated persistent disk (source: {resource.name})"
  type        = string
  default     = "{disk_zone}"
}}
''')
                    tfvars_lines.append(f'{name}_zone = "{disk_zone}"  # Inferred from source region')

                if resource.canonical_type is CanonicalResourceType.DNS_RECORD:
                    variable_blocks.append(f'''variable "{name}_managed_zone" {{
  description = "Name of the google_dns_managed_zone this record belongs to (source: {resource.name})"
  type        = string
  default     = ""
}}

variable "{name}_value" {{
  description = "Record data (source rrdatas value: {resource.name})"
  type        = string
  default     = ""
}}
''')
                    tfvars_lines.append(f'# {name}_managed_zone = "YOUR_MANAGED_ZONE_NAME"  # Set before apply')
                    tfvars_lines.append(f'# {name}_value = "YOUR_RECORD_VALUE"  # Set before apply')

            elif self.target_provider is CloudProvider.AWS:
                if resource.canonical_type is CanonicalResourceType.NETWORK_VPC:
                    variable_blocks.append(f'''variable "{name}_cidr_block" {{
  description = "AWS VPC CIDR block (GCP networks have no VPC-level CIDR of their own)"
  type        = string
  default     = "10.0.0.0/16"
}}
''')
                    tfvars_lines.append(
                        f'{name}_cidr_block = "10.0.0.0/16"  # Default — GCP source has no VPC-level CIDR, review before apply'
                    )

                if resource.canonical_type is CanonicalResourceType.NETWORK_SUBNET:
                    has_source_cidr = "ip_cidr_range" in resource.native_attributes
                    cidr = resource.native_attributes.get("ip_cidr_range", "10.0.1.0/24")
                    variable_blocks.append(f'''variable "{name}_cidr_block" {{
  description = "AWS subnet CIDR block (source ip_cidr_range: {cidr})"
  type        = string
  default     = "{cidr}"
}}

variable "{name}_availability_zone" {{
  description = "AWS availability zone (source region: {resource.native_attributes.get("region", "unknown")})"
  type        = string
  default     = "us-east-1a"
}}
''')
                    cidr_comment = "From source ip_cidr_range" if has_source_cidr else "Default — no source CIDR found"
                    tfvars_lines.append(f'{name}_cidr_block = "{cidr}"  # {cidr_comment}')
                    tfvars_lines.append(
                        f'# {name}_availability_zone = "YOUR_AZ"  '
                        f'# Set before apply — no AWS AZ equivalent in GCP source data'
                    )

                if resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                    variable_blocks.append(f'''variable "{name}_ami" {{
  description = "AMI ID for the migrated instance (GCP images cannot be booted directly on EC2)"
  type        = string
  default     = "ami-0abcdef1234567890"
}}
''')
                    tfvars_lines.append(f'# {name}_ami = "YOUR_AMI_ID"  # Set before apply')

                if resource.canonical_type is CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION:
                    variable_blocks.append(f'''variable "{name}_filename" {{
  description = "Path to the Lambda deployment package (source: Cloud Function {resource.name})"
  type        = string
  default     = "{name}.zip"
}}
''')
                    tfvars_lines.append(
                        f'# {name}_filename = "path/to/{name}.zip"  '
                        f'# Set before apply — package the Cloud Function source for Lambda'
                    )

                if resource.canonical_type is CanonicalResourceType.DATABASE_INSTANCE:
                    variable_blocks.append(f'''variable "{name}_db_name" {{
  description = "Initial database name (source: Cloud SQL instance {resource.name})"
  type        = string
  default     = "appdb"
}}

variable "{name}_username" {{
  description = "Master username for the migrated RDS instance"
  type        = string
  default     = "dbadmin"
}}

variable "{name}_password" {{
  description = "Master password for the migrated RDS instance — override in terraform.tfvars, never commit a real value"
  type        = string
  default     = "changeme-in-tfvars"
  sensitive   = true
}}
''')
                    tfvars_lines.append(f'{name}_db_name = "appdb"  # Default — review before apply')
                    tfvars_lines.append(f'{name}_username = "dbadmin"  # Default — review before apply')
                    tfvars_lines.append(
                        f'# {name}_password = "CHANGE_ME"  '
                        f'# sensitive - set via env var TF_VAR_{name}_password'
                    )

                if resource.canonical_type is CanonicalResourceType.STORAGE_BLOCK_VOLUME:
                    variable_blocks.append(f'''variable "{name}_availability_zone" {{
  description = "AWS availability zone for the migrated EBS volume (GCP zones have no AWS AZ equivalent)"
  type        = string
  default     = "us-east-1a"
}}
''')
                    tfvars_lines.append(
                        f'# {name}_availability_zone = "YOUR_AZ"  '
                        f'# Set before apply — no AWS AZ equivalent in GCP source data'
                    )

                if resource.canonical_type is CanonicalResourceType.DATABASE_NOSQL:
                    variable_blocks.append(f'''variable "{name}_hash_key" {{
  description = "DynamoDB partition key (source: Firestore database {resource.name} has no equivalent key schema)"
  type        = string
  default     = "id"
}}
''')
                    tfvars_lines.append(
                        f'# {name}_hash_key = "YOUR_PARTITION_KEY"  '
                        f'# Set before apply — Firestore has no partition-key equivalent, review your data model'
                    )

                if resource.canonical_type is CanonicalResourceType.NETWORK_ROUTE_TABLE:
                    variable_blocks.append(f'''variable "{name}_gateway_id" {{
  description = "Target gateway ID for the migrated route (source: {resource.name})"
  type        = string
  default     = ""
}}
''')
                    tfvars_lines.append(
                        f'# {name}_gateway_id = "YOUR_GATEWAY_ID"  '
                        f'# Set before apply — e.g. an aws_internet_gateway or aws_nat_gateway id'
                    )

                if resource.canonical_type is CanonicalResourceType.COMPUTE_CONTAINER_SERVICE:
                    variable_blocks.append(f'''variable "{name}_image" {{
  description = "Container image for the migrated ECS service (source: Cloud Run service {resource.name})"
  type        = string
  default     = "public.ecr.aws/docker/library/hello-world:latest"
}}
''')
                    tfvars_lines.append(f'# {name}_image = "YOUR_IMAGE"  # Set before apply — default is a placeholder')

                if resource.canonical_type is CanonicalResourceType.NETWORK_PEERING:
                    variable_blocks.append(f'''variable "{name}_peer_vpc_id" {{
  description = "Peer VPC ID (source: GCP network peering {resource.name})"
  type        = string
  default     = ""
}}
''')
                    tfvars_lines.append(f'# {name}_peer_vpc_id = "YOUR_PEER_VPC_ID"  # Set before apply')

                if resource.canonical_type is CanonicalResourceType.DNS_RECORD:
                    variable_blocks.append(f'''variable "{name}_zone_id" {{
  description = "Route53 hosted zone ID this record belongs to (source: {resource.name})"
  type        = string
  default     = ""
}}

variable "{name}_value" {{
  description = "Record data (source rrdatas value: {resource.name})"
  type        = string
  default     = ""
}}
''')
                    tfvars_lines.append(f'# {name}_zone_id = "YOUR_HOSTED_ZONE_ID"  # Set before apply')
                    tfvars_lines.append(f'# {name}_value = "YOUR_RECORD_VALUE"  # Set before apply')

            generated_count += 1

        if gcp_ctx is not None and gcp_ctx.used_default_subnet:
            main_blocks.insert(
                0,
                '''data "google_compute_subnetwork" "default" {
  name   = "default"
  region = var.region
}
''',
            )

        if gcp_ctx is not None and gcp_ctx.used_default_network:
            main_blocks.insert(
                0,
                '''data "google_compute_network" "default" {
  name = "default"
}
''',
            )

        if aws_ctx is not None and aws_ctx.used_default_subnet:
            main_blocks.insert(
                0,
                f'''data "aws_subnets" "default" {{
  filter {{
    name   = "vpc-id"
    values = [{aws_ctx.vpc_id_expr()}]
  }}
}}
''',
            )

        if aws_ctx is not None and aws_ctx.used_default_vpc:
            main_blocks.insert(
                0,
                '''data "aws_vpc" "default" {
  default = true
}
''',
            )

        files = [
            GeneratedFile(
                filename="main.tf",
                content="\n".join(main_blocks),
                description="Primary resource definitions",
            ),
            GeneratedFile(
                filename="variables.tf",
                content="\n".join(variable_blocks),
                description="Input variables for all migrated resources",
            ),
            GeneratedFile(
                filename="outputs.tf",
                content=self._generate_outputs(graph, translation_index),
                description="Output values",
            ),
            GeneratedFile(
                filename="providers.tf",
                content=self._generate_providers(),
                description="Provider configuration",
            ),
            GeneratedFile(
                filename="versions.tf",
                content=self._generate_versions(),
                description="Required provider versions",
            ),
            GeneratedFile(
                filename="backend.tf",
                content=self._generate_backend(),
                description="State backend configuration",
            ),
            GeneratedFile(
                filename="terraform.tfvars",
                content=self._generate_tfvars(tfvars_lines),
                description="Variable overrides, pre-filled from the source infrastructure",
            ),
            GeneratedFile(
                filename="MIGRATION_GUIDE.md",
                content=self._generate_migration_guide(
                    translation.source_provider.value,
                    self.target_provider.value,
                    generated_count,
                ),
                description="Migration guide and deployment instructions",
            ),
        ]

        report = TerraformGenerationReport(
            target_provider=self.target_provider,
            files=files,
            generated_resources=generated_count,
            skipped_resources=skipped_count,
            import_blocks=import_blocks,
        )

        logger.info(
            "terraform_generation_completed",
            target_provider=self.target_provider.value,
            generated=generated_count,
            skipped=skipped_count,
            files=len(files),
        )
        return report

    def _generate_tfvars(self, tfvars_lines: list[str]) -> str:
        provider_override = (
            '# aws_region = "us-east-1"\n'
            if self.target_provider is CloudProvider.AWS
            else f'# project_id = "{self.project_id}"\n'
        )
        header = (
            "# Variable overrides for this migration.\n"
            "# Active lines were extracted or mapped from the source infrastructure.\n"
            "# Commented-out lines have no source equivalent -- set a real value\n"
            "# before `terraform apply`.\n"
        )
        if not tfvars_lines:
            return header + provider_override
        return header + provider_override + "\n" + "\n".join(tfvars_lines) + "\n"

    def _generate_migration_guide(
        self,
        source_provider: str,
        target_provider: str,
        resource_count: int,
    ) -> str:
        return f"""# Migration Guide
Generated by Migration Factory v2.0.3

## Quick Start
```bash
# 1. Initialize (uses local state by default)
terraform init

# 2. Review what will be created
terraform plan -out=migration.plan

# 3. Review the plan output carefully, then apply
terraform apply migration.plan
```

## Before Applying - Required Manual Steps

### 1. Set sensitive variables
Never put passwords in terraform.tfvars. Use environment variables:
```bash
export TF_VAR_db_password="your-password"
export TF_VAR_db_username="your-username"
```

### 2. Fill placeholder values
Search terraform.tfvars for CHANGE_ME and YOUR_* and replace them.

### 3. Configure backend (for team use)
Uncomment and configure backend.tf for remote state.

### 4. Apply in order (recommended)
Apply networking first, then compute:
```bash
terraform apply -target=google_compute_network.main
terraform apply -target=google_compute_subnetwork.app
terraform apply  # apply everything else
```

## Known Manual Steps Required

- **IAM permissions**: Roles are created but policies need manual review
- **Secret values**: Created in Secret Manager but values must be added manually
- **SSL certificates**: Certificate resources created but domain validation required
- **DNS cutover**: Update NS records at registrar LAST (causes downtime)

## Resource Summary
- Source: {source_provider.upper()}
- Target: {target_provider.upper()}
- Resources: {resource_count}

## Cost Note
Monthly costs shown are ESTIMATES based on on-demand pricing.
Actual costs depend on usage patterns and any discounts.

## After Migration
1. Validate all services are running correctly
2. Update DNS records to point to new infrastructure
3. Run your test suite against new environment
4. Decommission old infrastructure after validation period

## Support

Generated by: Migration Factory
"""

    def write(self, report: TerraformGenerationReport, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for gen_file in report.files:
            (output_dir / gen_file.filename).write_text(gen_file.content, encoding="utf-8")
        logger.info("terraform_files_written", output_dir=str(output_dir), file_count=len(report.files))

    def _generate_providers(self) -> str:
        # required_providers lives here, not in versions.tf -- Terraform
        # rejects a module that declares it in more than one file
        # ("Duplicate required providers configuration"), and
        # test_bidirectional.py asserts "hashicorp/aws" appears in
        # providers.tf specifically. versions.tf carries only
        # required_version (see _generate_versions below).
        if self.target_provider is CloudProvider.AWS:
            return '''terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}
'''
        return f'''terraform {{
  required_version = ">= 1.5.0"

  required_providers {{
    google = {{
      source  = "hashicorp/google"
      version = "~> 5.0"
    }}
  }}
}}

provider "google" {{
  project = var.project_id
  region  = var.region
}}

variable "project_id" {{
  description = "GCP project ID"
  type        = string
  default     = "{self.project_id}"
}}

variable "region" {{
  description = "GCP region for deployment"
  type        = string
  default     = "{self.region}"
}}
'''

    def _generate_versions(self) -> str:
        # Required provider versions live in providers.tf (see above) so
        # they can't be declared twice -- this file is kept only so
        # `versions.tf` still exists as a filename some tooling expects.
        return "# Terraform version constraints are in providers.tf\n"

    def _generate_backend(self) -> str:
        # Backend blocks cannot reference variables, locals, or any other
        # computed value -- the bucket name has to be a literal string
        # pointing at a bucket that doesn't exist yet, which previously made
        # `terraform init` fail immediately (it tries to configure the
        # backend even before the bucket is real). Commented out by default
        # so init works against local state right away; uncomment once a
        # real state bucket exists.
        if self.target_provider is CloudProvider.AWS:
            return '''terraform {
  # Remote state configuration (commented out by default).
  # Uncomment and configure before running terraform apply.
  # Create the bucket first: aws s3 mb s3://YOUR_BUCKET_NAME-tfstate
  #
  # backend "s3" {
  #   bucket = "YOUR_BUCKET_NAME-tfstate"
  #   key    = "migration-factory/terraform.tfstate"
  #   region = "us-east-1"
  # }
}
'''
        return f'''terraform {{
  # Remote state configuration (commented out by default).
  # Uncomment and configure before running terraform apply.
  # Create the bucket first: gsutil mb gs://{self.project_id}-tfstate
  #
  # backend "gcs" {{
  #   bucket = "{self.project_id}-tfstate"
  #   prefix = "migration-factory/state"
  # }}
}}
'''

    def _generate_outputs(
        self,
        graph: CanonicalInfrastructureGraph,
        translation_index: dict[str, TranslationResult],
    ) -> str:
        blocks: list[str] = []
        for resource in graph.resources.values():
            tr = translation_index.get(resource.id)
            if tr is None or tr.status is SupportStatus.UNSUPPORTED:
                continue
            name = _tf_name(resource)
            if self.target_provider is CloudProvider.AWS:
                if resource.canonical_type is CanonicalResourceType.NETWORK_VPC:
                    blocks.append(f'''output "{name}_id" {{
  description = "VPC ID of the migrated network"
  value       = aws_vpc.{name}.id
}}
''')
                elif resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                    blocks.append(f'''output "{name}_instance_id" {{
  description = "EC2 instance ID"
  value       = aws_instance.{name}.id
}}

output "{name}_private_ip" {{
  description = "Private IP address"
  value       = aws_instance.{name}.private_ip
}}
''')
                elif resource.canonical_type is CanonicalResourceType.STORAGE_OBJECT_BUCKET:
                    blocks.append(f'''output "{name}_bucket_name" {{
  description = "S3 bucket name"
  value       = aws_s3_bucket.{name}.bucket
}}
''')
                elif resource.canonical_type is CanonicalResourceType.DATABASE_INSTANCE:
                    blocks.append(f'''output "{name}_endpoint" {{
  description = "RDS instance connection endpoint"
  value       = aws_db_instance.{name}.endpoint
}}
''')
            else:
                if resource.canonical_type is CanonicalResourceType.NETWORK_VPC:
                    blocks.append(f'''output "{name}_id" {{
  description = "VPC network ID of the migrated resource"
  value       = google_compute_network.{name}.id
}}
''')
                elif resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                    blocks.append(f'''output "{name}_instance_id" {{
  description = "Instance ID of migrated compute instance"
  value       = google_compute_instance.{name}.id
}}

output "{name}_internal_ip" {{
  description = "Internal IP address"
  value       = google_compute_instance.{name}.network_interface[0].network_ip
}}
''')
                elif resource.canonical_type is CanonicalResourceType.STORAGE_OBJECT_BUCKET:
                    blocks.append(f'''output "{name}_bucket_url" {{
  description = "GCS bucket URL"
  value       = google_storage_bucket.{name}.url
}}
''')
                elif resource.canonical_type is CanonicalResourceType.DATABASE_INSTANCE:
                    blocks.append(f'''output "{name}_connection_name" {{
  description = "Cloud SQL connection name for Cloud SQL Proxy"
  value       = google_sql_database_instance.{name}.connection_name
}}
''')
        return "\n".join(blocks) if blocks else "# No outputs generated\n"

    def generate_import_blocks(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
    ) -> GeneratedFile:
        """Generate terraform import blocks for existing resources."""
        translation_index = {tr.resource_id: tr for tr in translation.results}
        blocks: list[str] = []

        for resource in graph.resources.values():
            tr = translation_index.get(resource.id)
            if tr is None or tr.status is SupportStatus.UNSUPPORTED:
                continue
            name = _tf_name(resource)
            for tf_type in tr.target_terraform_types[:1]:
                source_id = resource.native_attributes.get("id") or resource.name
                blocks.append(f'import {{\n  to = {tf_type}.{name}\n  id = "{source_id}"\n}}\n')

        return GeneratedFile(
            filename="imports.tf",
            content="\n".join(blocks) if blocks else "# No import blocks generated\n",
            description="Terraform import blocks for existing resources",
        )

    def generate_module_structure(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
    ) -> list[GeneratedFile]:
        """Generate a modular Terraform structure with one module per resource category."""
        modules: dict[str, list[str]] = {}

        for resource in graph.resources.values():
            category = resource.canonical_type.value.split(".")[0]
            modules.setdefault(category, []).append(resource.id)

        files: list[GeneratedFile] = []
        module_calls: list[str] = []

        for module_name, resource_ids in sorted(modules.items()):
            module_calls.append(f'module "{module_name}" {{\n  source = "./modules/{module_name}"\n}}\n')
            files.append(GeneratedFile(
                filename=f"modules/{module_name}/main.tf",
                content=f"# {module_name} module - {len(resource_ids)} resources\n# Resources: {', '.join(resource_ids[:10])}\n",
                description=f"Module for {module_name} resources",
            ))

        files.append(GeneratedFile(
            filename="main_modular.tf",
            content="\n".join(module_calls),
            description="Root module calling per-category sub-modules",
        ))

        return files
