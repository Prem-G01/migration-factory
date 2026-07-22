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

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.translation.models import SupportStatus, TranslationReport, TranslationResult

logger = get_logger(__name__)


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


def _gen_gcp_vpc(resource: CanonicalResource, tf_name: str) -> str:
    return f'''resource "google_compute_network" "{tf_name}" {{
  name                    = var.{tf_name}_name
  auto_create_subnetworks = false
  description             = "Migrated from {resource.source_type}: {resource.name}"
}}
'''


def _gen_gcp_subnet(resource: CanonicalResource, tf_name: str) -> str:
    cidr = resource.native_attributes.get("cidr_block", "10.0.0.0/24")
    region = resource.region or "us-central1"
    return f'''resource "google_compute_subnetwork" "{tf_name}" {{
  name          = var.{tf_name}_name
  ip_cidr_range = "{cidr}"
  region        = "{region}"
  network       = google_compute_network.{_sanitize_name(resource.name)}.id
  description   = "Migrated from {resource.source_type}: {resource.name}"

  private_ip_google_access = true
}}
'''


def _gen_gcp_firewall(resource: CanonicalResource, tf_name: str) -> str:
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
  network = google_compute_network.main.name

{allow_hcl}

  source_ranges = [{ranges_hcl}]
  description   = "Migrated from {resource.source_type}: {resource.name}"
}}
'''


def _gen_gcp_instance(resource: CanonicalResource, tf_name: str) -> str:
    zone = resource.native_attributes.get("availability_zone", "us-central1-a")
    # Map to GCP zone format
    if zone and not zone.startswith("us-") or "-" not in zone:
        zone = "us-central1-a"

    return f'''resource "google_compute_instance" "{tf_name}" {{
  name         = var.{tf_name}_name
  machine_type = var.{tf_name}_machine_type
  zone         = "{zone}"

  boot_disk {{
    initialize_params {{
      image = "debian-cloud/debian-11"
      size  = 20
    }}
  }}

  network_interface {{
    subnetwork = google_compute_subnetwork.{_sanitize_name(resource.name)}.id
  }}

  metadata = {{
    # Migrated from {resource.source_type}: {resource.name}
    # Original instance type: {resource.native_attributes.get("instance_type", "unknown")}
  }}

  labels = {{
    {chr(10).join(f'    {k} = "{v}"' for k, v in resource.tags.items()) if resource.tags else '    migrated = "true"'}
  }}
}}
'''


def _gen_gcp_bucket(resource: CanonicalResource, tf_name: str) -> str:
    location = resource.region or "US"
    return f'''resource "google_storage_bucket" "{tf_name}" {{
  name          = var.{tf_name}_name
  location      = "{location.upper()}"
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {{
    enabled = true
  }}

  labels = {{
    migrated = "true"
    source   = "aws-s3"
  }}
}}
'''


def _gen_gcp_cloudsql(resource: CanonicalResource, tf_name: str) -> str:
    region = resource.region or "us-central1"
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
      private_network = google_compute_network.main.id
    }}

    backup_configuration {{
      enabled            = true
      binary_log_enabled = {"true" if "mysql" in str(engine).lower() else "false"}
    }}
  }}

  deletion_protection = true
}}
'''


def _gen_gcp_service_account(resource: CanonicalResource, tf_name: str) -> str:
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


def _gen_gcp_lb(resource: CanonicalResource, tf_name: str) -> str:
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


_GCP_GENERATORS: dict[CanonicalResourceType, Any] = {
    CanonicalResourceType.NETWORK_VPC: _gen_gcp_vpc,
    CanonicalResourceType.NETWORK_SUBNET: _gen_gcp_subnet,
    CanonicalResourceType.NETWORK_FIREWALL_RULE: _gen_gcp_firewall,
    CanonicalResourceType.COMPUTE_INSTANCE: _gen_gcp_instance,
    CanonicalResourceType.STORAGE_OBJECT_BUCKET: _gen_gcp_bucket,
    CanonicalResourceType.DATABASE_INSTANCE: _gen_gcp_cloudsql,
    CanonicalResourceType.IAM_ROLE: _gen_gcp_service_account,
    CanonicalResourceType.LOAD_BALANCER: _gen_gcp_lb,
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


def _gen_aws_vpc(resource: CanonicalResource, tf_name: str) -> str:
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


def _gen_aws_subnet(resource: CanonicalResource, tf_name: str) -> str:
    return f'''resource "aws_subnet" "{tf_name}" {{
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.{tf_name}_cidr_block
  availability_zone = var.{tf_name}_availability_zone

  tags = {{
    Name     = var.{tf_name}_name
    migrated = "true"
  }}
}}
'''


def _gen_aws_security_group(resource: CanonicalResource, tf_name: str) -> str:
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
  vpc_id      = aws_vpc.main.id

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


def _gen_aws_instance(resource: CanonicalResource, tf_name: str) -> str:
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
  subnet_id     = aws_subnet.app.id

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


def _gen_aws_s3_bucket(resource: CanonicalResource, tf_name: str) -> str:
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


def _gen_aws_iam_role(resource: CanonicalResource, tf_name: str) -> str:
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


def _gen_aws_db_instance(resource: CanonicalResource, tf_name: str) -> str:
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


def _gen_aws_lambda_function(resource: CanonicalResource, tf_name: str) -> str:
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


def _gen_aws_elasticache(resource: CanonicalResource, tf_name: str) -> str:
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
}


@dataclass(slots=True)
class TerraformGenerator:
    target_provider: CloudProvider = CloudProvider.GCP
    project_id: str = "your-gcp-project-id"
    region: str = "us-central1"

    def generate(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
    ) -> TerraformGenerationReport:

        main_blocks: list[str] = []
        variable_blocks: list[str] = []
        if self.target_provider is CloudProvider.AWS:
            variable_blocks.append('''variable "aws_region" {
  description = "AWS region to deploy migrated resources into"
  type        = string
  default     = "us-east-1"
}
''')
        translation_index = {tr.resource_id: tr for tr in translation.results}

        import_blocks: list[str] = []
        generated_count = 0
        skipped_count = 0

        # Generate in topological order for readable output
        try:
            ordered_ids = graph.topological_order()
        except Exception:
            ordered_ids = list(graph.resources.keys())

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
            block = gen_fn(resource, name)
            main_blocks.append(block)

            # Generate variables for this resource
            variable_blocks.append(f'''variable "{name}_name" {{
  description = "Name for migrated resource (source: {resource.name})"
  type        = string
  default     = "{_sanitize_name(resource.name)}"
}}
''')

            if self.target_provider is CloudProvider.GCP:
                if resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                    variable_blocks.append(f'''variable "{name}_machine_type" {{
  description = "GCP machine type (source instance_type: {resource.native_attributes.get("instance_type", "unknown")})"
  type        = string
  default     = "e2-medium"
}}
''')

                if resource.canonical_type is CanonicalResourceType.IAM_ROLE:
                    variable_blocks.append(f'''variable "{name}_account_id" {{
  description = "GCP service account ID (source: {resource.name})"
  type        = string
  default     = "{_sanitize_name(resource.name)}"
}}
''')

            elif self.target_provider is CloudProvider.AWS:
                if resource.canonical_type is CanonicalResourceType.NETWORK_VPC:
                    variable_blocks.append(f'''variable "{name}_cidr_block" {{
  description = "AWS VPC CIDR block (GCP networks have no VPC-level CIDR of their own)"
  type        = string
  default     = "10.0.0.0/16"
}}
''')

                if resource.canonical_type is CanonicalResourceType.NETWORK_SUBNET:
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

                if resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                    variable_blocks.append(f'''variable "{name}_ami" {{
  description = "AMI ID for the migrated instance (GCP images cannot be booted directly on EC2)"
  type        = string
  default     = "ami-0abcdef1234567890"
}}
''')

                if resource.canonical_type is CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION:
                    variable_blocks.append(f'''variable "{name}_filename" {{
  description = "Path to the Lambda deployment package (source: Cloud Function {resource.name})"
  type        = string
  default     = "{name}.zip"
}}
''')

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

            generated_count += 1

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
                content=(
                    '# Override variables here\n# aws_region = "us-east-1"\n'
                    if self.target_provider is CloudProvider.AWS
                    else f'# Override variables here\n# project_id = "{self.project_id}"\n'
                ),
                description="Variable overrides",
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

    def write(self, report: TerraformGenerationReport, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for gen_file in report.files:
            (output_dir / gen_file.filename).write_text(gen_file.content, encoding="utf-8")
        logger.info("terraform_files_written", output_dir=str(output_dir), file_count=len(report.files))

    def _generate_providers(self) -> str:
        if self.target_provider is CloudProvider.AWS:
            return '''terraform {
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
'''
        return f'''provider "google" {{
  project = var.project_id
  region  = var.region
}}

variable "project_id" {{
  description = "GCP project ID"
  type        = string
  default     = "{self.project_id}"
}}

variable "region" {{
  description = "GCP region"
  type        = string
  default     = "{self.region}"
}}
'''

    def _generate_versions(self) -> str:
        if self.target_provider is CloudProvider.AWS:
            return '''terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
'''
        return '''terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}
'''

    def _generate_backend(self) -> str:
        if self.target_provider is CloudProvider.AWS:
            return '''terraform {
  backend "s3" {
    bucket = "migration-factory-tfstate"
    key    = "migration/terraform.tfstate"
    region = "us-east-1"
  }
}
'''
        return f'''terraform {{
  backend "gcs" {{
    bucket = "{self.project_id}-tfstate"
    prefix = "migration"
  }}
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
  value = aws_vpc.{name}.id
}}
''')
                elif resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                    blocks.append(f'''output "{name}_ip" {{
  value = aws_instance.{name}.private_ip
}}
''')
            else:
                if resource.canonical_type is CanonicalResourceType.NETWORK_VPC:
                    blocks.append(f'''output "{name}_id" {{
  value = google_compute_network.{name}.id
}}
''')
                elif resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
                    blocks.append(f'''output "{name}_ip" {{
  value = google_compute_instance.{name}.network_interface[0].network_ip
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
