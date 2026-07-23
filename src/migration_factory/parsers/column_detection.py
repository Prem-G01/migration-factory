"""Shared "flexible inventory row" logic for CSVInventoryParser and
ExcelInventoryParser.

Real-world CSV/Excel exports never use the canonical `type,name,id,provider`
headers exactly — this module maps a wide range of real-world column names
(InstanceId, ResourceType, Asset Type, ...) onto the five fields a
ParsedResource needs, and infers whatever it can't find a column for
(resource type from an instance-type value, provider from a region format).
"""

from __future__ import annotations

import re
from typing import Any

from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.base import ParsedResource

# ---------------------------------------------------------------------------
# Column name aliases (normalized: lowercase, spaces/./: -> underscore)
# ---------------------------------------------------------------------------

TYPE_ALIASES = {
    "resource_type", "resourcetype", "asset_type", "assettype",
    "service", "service_type", "servicetype",
}
NAME_ALIASES = {
    "resource_name", "resourcename", "display_name", "displayname",
    "asset_name", "assetname", "title", "label", "friendly_name",
    "tag_name", "tags_name",
}
ID_ALIASES = {
    "resource_id", "resourceid", "asset_id", "assetid",
    "instance_id", "identifier", "resource_identifier", "arn",
}
PROVIDER_ALIASES = {
    "cloud", "cloud_provider", "cloudprovider", "platform",
    "vendor", "source", "environment_type",
}
REGION_ALIASES = {
    "location", "zone", "availability_zone", "az",
    "aws_region", "gcp_region",
}

DEPENDS_ALIASES = {"depends_on", "dependson", "dependencies"}

# ---------------------------------------------------------------------------
# Resource-type inference
# ---------------------------------------------------------------------------

_AWS_INSTANCE_TYPE_RE = re.compile(r"^[a-z]{1,3}\d[a-z0-9]*\.(nano|micro|small|medium|\d*x?large|metal)$", re.IGNORECASE)
_GCP_MACHINE_TYPE_RE = re.compile(
    r"^(e2|n1|n2|n2d|n4|c2|c2d|c3|c3d|c4|m1|m2|m3|t2a|t2d|a2|a3|g2)-", re.IGNORECASE
)

# Longer/more specific phrases first — first match wins.
_RESOURCE_TYPE_DESCRIPTIONS: list[tuple[str, str]] = [
    ("rds db instance", "aws_db_instance"),
    ("simple storage service", "aws_s3_bucket"),
    ("s3 bucket", "aws_s3_bucket"),
    ("ec2 instance", "aws_instance"),
    ("virtual private cloud", "aws_vpc"),
    ("elastic kubernetes service", "aws_eks_cluster"),
    ("lambda function", "aws_lambda_function"),
    ("iam role", "aws_iam_role"),
    ("security group", "aws_security_group"),
    ("subnet", "aws_subnet"),
    ("rds", "aws_db_instance"),
    ("vpc", "aws_vpc"),
    ("eks", "aws_eks_cluster"),
    ("lambda", "aws_lambda_function"),
    ("gce instance", "google_compute_instance"),
    ("compute instance", "google_compute_instance"),
    ("gcs bucket", "google_storage_bucket"),
    ("cloud storage", "google_storage_bucket"),
    ("gke cluster", "google_container_cluster"),
    ("kubernetes cluster", "google_container_cluster"),
    ("cloud sql", "google_sql_database_instance"),
    ("sql instance", "google_sql_database_instance"),
    ("cloud function", "google_cloudfunctions2_function"),
    ("pub/sub", "google_pubsub_topic"),
    ("pubsub", "google_pubsub_topic"),
]

_TF_TYPE_RE = re.compile(r"^(aws|google|azurerm)_[a-z0-9_]+$", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Provider inference
# ---------------------------------------------------------------------------

_AWS_REGION_RE = re.compile(r"^[a-z]{2}-[a-z]+-\d$")
_GCP_REGION_RE = re.compile(r"^[a-z]+-[a-z]+\d(-[a-z])?$")
_AZURE_REGIONS = {
    "eastus", "eastus2", "westus", "westus2", "westus3", "centralus",
    "northcentralus", "southcentralus", "westcentralus", "westeurope",
    "northeurope", "southeastasia", "eastasia", "japaneast", "japanwest",
    "australiaeast", "australiasoutheast", "uksouth", "ukwest",
    "canadacentral", "canadaeast", "brazilsouth", "centralindia",
    "southindia", "koreacentral", "koreasouth", "francecentral",
    "germanywestcentral",
}


def normalize_header(header: str) -> str:
    """Lowercase, strip BOM/whitespace, and fold spaces/./: to underscore
    so 'Asset Type', 'tags.name', and 'tag:name' all match their alias set.
    """
    h = header.lstrip("﻿").strip().lower()
    for ch in (" ", ".", ":", "-"):
        h = h.replace(ch, "_")
    while "__" in h:
        h = h.replace("__", "_")
    return h.strip("_")


def _collapse(s: str) -> str:
    """Drop underscores entirely so 'aws_region' and a fused PascalCase
    header like 'AwsRegion' (normalize_header -> 'awsregion', no separator
    to fold) still compare equal.
    """
    return s.replace("_", "")


def _find_header(norm_to_orig: dict[str, str], canonical: str, aliases: set[str]) -> str | None:
    """Exact canonical name first, then aliases, then an underscore-blind
    comparison — first header in insertion order wins within each phase.
    """
    if canonical in norm_to_orig:
        return norm_to_orig[canonical]
    for norm, orig in norm_to_orig.items():
        if norm in aliases:
            return orig
    collapsed_targets = {_collapse(a) for a in aliases} | {_collapse(canonical)}
    for norm, orig in norm_to_orig.items():
        if _collapse(norm) in collapsed_targets:
            return orig
    return None


def _map_description_to_type(value: str) -> str | None:
    lowered = value.strip().lower()
    for phrase, tf_type in _RESOURCE_TYPE_DESCRIPTIONS:
        if phrase in lowered:
            return tf_type
    return None


def _resolve_resource_type(type_val: str | None, row: dict[str, str], norm_to_orig: dict[str, str]) -> str:
    if type_val:
        mapped = _map_description_to_type(type_val)
        if mapped:
            return mapped
        if _TF_TYPE_RE.match(type_val.strip()):
            return type_val.strip().lower()

    instance_type_header = norm_to_orig.get("instancetype") or norm_to_orig.get("instance_type")
    if instance_type_header:
        val = (row.get(instance_type_header) or "").strip()
        if val and _AWS_INSTANCE_TYPE_RE.match(val):
            return "aws_instance"

    machine_type_header = norm_to_orig.get("machinetype") or norm_to_orig.get("machine_type")
    if machine_type_header:
        val = (row.get(machine_type_header) or "").strip()
        last_segment = val.rsplit("/", 1)[-1] if val else ""
        if last_segment and _GCP_MACHINE_TYPE_RE.match(last_segment):
            return "google_compute_instance"

    return type_val if type_val else "unknown"


def _resolve_provider(
    provider_val: str | None, resource_type: str, region_val: str | None, raw_values: list[str]
) -> CloudProvider:
    if provider_val:
        v = provider_val.strip().lower()
        if re.search(r"\baws\b|\bamazon\b", v):
            return CloudProvider.AWS
        if re.search(r"\bgcp\b|\bgoogle\b", v):
            return CloudProvider.GCP
        if "azure" in v:
            return CloudProvider.AZURE
        if v in {e.value for e in CloudProvider}:
            return CloudProvider(v)

    if resource_type.startswith("aws_"):
        return CloudProvider.AWS
    if resource_type.startswith("google_"):
        return CloudProvider.GCP
    if resource_type.startswith("azurerm_"):
        return CloudProvider.AZURE

    if region_val:
        r = region_val.strip().lower()
        if _AWS_REGION_RE.match(r):
            return CloudProvider.AWS
        if _GCP_REGION_RE.match(r):
            return CloudProvider.GCP
        if r in _AZURE_REGIONS:
            return CloudProvider.AZURE

    for v in raw_values:
        if not isinstance(v, str) or not v:
            continue
        lv = v.lower()
        if re.search(r"\baws\b|\bamazon\b", lv):
            return CloudProvider.AWS
        if re.search(r"\bgcp\b|\bgoogle\b", lv):
            return CloudProvider.GCP

    return CloudProvider.UNKNOWN


def build_resource_from_row(row: dict[str, str], row_num: int, source_path: str) -> ParsedResource | None:
    """Turn one CSV/Excel row (original-header -> string value) into a
    ParsedResource, applying alias detection + inference. Returns None for a
    row that's entirely empty (caller should skip it, not count it as a
    warning).
    """
    if not any(v.strip() for v in row.values() if isinstance(v, str)):
        return None

    norm_to_orig: dict[str, str] = {}
    for h in row:
        norm_to_orig[normalize_header(h)] = h

    def _get(canonical: str, aliases: set[str]) -> str | None:
        header = _find_header(norm_to_orig, canonical, aliases)
        if header is None:
            return None
        val = row.get(header)
        return val.strip() if val else None

    type_val = _get("type", TYPE_ALIASES)
    name_val = _get("name", NAME_ALIASES)
    id_val = _get("id", ID_ALIASES)
    provider_val = _get("provider", PROVIDER_ALIASES)
    region_val = _get("region", REGION_ALIASES)
    depends_val = _get("depends_on", DEPENDS_ALIASES)

    resource_type = _resolve_resource_type(type_val, row, norm_to_orig)
    provider = _resolve_provider(provider_val, resource_type, region_val, list(row.values()))

    name = name_val or id_val or f"row-{row_num}"
    resource_id = id_val or name_val or f"row-{row_num}"

    consumed = {
        _find_header(norm_to_orig, "type", TYPE_ALIASES),
        _find_header(norm_to_orig, "name", NAME_ALIASES),
        _find_header(norm_to_orig, "id", ID_ALIASES),
        _find_header(norm_to_orig, "provider", PROVIDER_ALIASES),
        _find_header(norm_to_orig, "depends_on", DEPENDS_ALIASES),
    }
    consumed.discard(None)

    attrs: dict[str, Any] = {k: v for k, v in row.items() if k not in consumed}
    depends = [d.strip() for d in (depends_val or "").split(",") if d.strip()]

    return ParsedResource(
        source_provider=provider,
        source_type=resource_type,
        source_identifier=resource_id,
        name=name,
        attributes=attrs,
        raw_depends_on=depends,
        source_path=source_path,
    )
