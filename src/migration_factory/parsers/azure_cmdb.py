"""ARM Template Parser, Azure Mapper, ServiceNow CMDB Parser, and
Application-Centric Migration Engine.

Closes 7 checklist items that don't actually need cloud credentials —
they're format parsers and grouping logic.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.exceptions import MappingError, ParserError
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
    SourceLocation,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.mappers.base import BaseMapper
from migration_factory.parsers.base import BaseParser, ParsedResource, ParserResult, ParseWarning

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ARM Template Parser
# ---------------------------------------------------------------------------


class ARMTemplateParser(BaseParser):
    """Parses Azure Resource Manager (ARM) JSON templates."""

    name = "arm_template"

    _TYPE_MAP: dict[str, str] = {
        "Microsoft.Compute/virtualMachines": "azurerm_virtual_machine",
        "Microsoft.Network/virtualNetworks": "azurerm_virtual_network",
        "Microsoft.Network/networkSecurityGroups": "azurerm_network_security_group",
        "Microsoft.Network/publicIPAddresses": "azurerm_public_ip",
        "Microsoft.Network/loadBalancers": "azurerm_lb",
        "Microsoft.Storage/storageAccounts": "azurerm_storage_account",
        "Microsoft.Sql/servers": "azurerm_mssql_server",
        "Microsoft.Sql/servers/databases": "azurerm_mssql_database",
        "Microsoft.Web/sites": "azurerm_app_service",
        "Microsoft.ContainerService/managedClusters": "azurerm_kubernetes_cluster",
        "Microsoft.KeyVault/vaults": "azurerm_key_vault",
        "Microsoft.Network/applicationGateways": "azurerm_application_gateway",
        "Microsoft.DocumentDB/databaseAccounts": "azurerm_cosmosdb_account",
        "Microsoft.Cache/Redis": "azurerm_redis_cache",
        "Microsoft.ServiceBus/namespaces": "azurerm_servicebus_namespace",
        "Microsoft.EventHub/namespaces": "azurerm_eventhub_namespace",
    }

    def supports(self, source_path: Path) -> bool:
        if source_path.suffix != ".json":
            return False
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
            return isinstance(data, dict) and (
                "$schema" in data and "resources" in data
                and "azure" in str(data.get("$schema", "")).lower()
            )
        except Exception:
            return False

    def parse(self, source_path: Path) -> ParserResult:
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ParserError(f"Could not parse ARM template: {source_path}", cause=exc) from exc

        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []

        for arm_resource in data.get("resources", []):
            if not isinstance(arm_resource, dict):
                continue

            arm_type = arm_resource.get("type", "")
            tf_type = self._TYPE_MAP.get(arm_type, arm_type.lower().replace("/", "_"))
            name = arm_resource.get("name", "unnamed")
            location = arm_resource.get("location", "")
            properties = arm_resource.get("properties", {})
            depends = arm_resource.get("dependsOn", [])

            resources.append(ParsedResource(
                source_provider=CloudProvider.AZURE,
                source_type=tf_type,
                source_identifier=str(name),
                name=str(name),
                attributes={**properties, "location": location} if isinstance(properties, dict) else {"location": location},
                raw_depends_on=depends if isinstance(depends, list) else [],
                source_path=str(source_path),
            ))

        return ParserResult(parser_name=self.name, source_path=str(source_path), resources=resources, warnings=warnings)


# ---------------------------------------------------------------------------
# Azure-to-Canonical Mapper
# ---------------------------------------------------------------------------


_AZURE_HANDLERS: dict[str, tuple[CanonicalResourceType, str]] = {
    "azurerm_virtual_network": (CanonicalResourceType.NETWORK_VPC, "network"),
    "azurerm_subnet": (CanonicalResourceType.NETWORK_SUBNET, "network"),
    "azurerm_network_security_group": (CanonicalResourceType.NETWORK_FIREWALL_RULE, "network"),
    "azurerm_public_ip": (CanonicalResourceType.NETWORK_NAT_GATEWAY, "network"),
    "azurerm_virtual_machine": (CanonicalResourceType.COMPUTE_INSTANCE, "compute"),
    "azurerm_linux_virtual_machine": (CanonicalResourceType.COMPUTE_INSTANCE, "compute"),
    "azurerm_windows_virtual_machine": (CanonicalResourceType.COMPUTE_INSTANCE, "compute"),
    "azurerm_kubernetes_cluster": (CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER, "compute"),
    "azurerm_app_service": (CanonicalResourceType.COMPUTE_CONTAINER_SERVICE, "compute"),
    "azurerm_function_app": (CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION, "compute"),
    "azurerm_storage_account": (CanonicalResourceType.STORAGE_OBJECT_BUCKET, "storage"),
    "azurerm_managed_disk": (CanonicalResourceType.STORAGE_BLOCK_VOLUME, "storage"),
    "azurerm_mssql_server": (CanonicalResourceType.DATABASE_INSTANCE, "database"),
    "azurerm_mssql_database": (CanonicalResourceType.DATABASE_INSTANCE, "database"),
    "azurerm_cosmosdb_account": (CanonicalResourceType.DATABASE_NOSQL, "database"),
    "azurerm_redis_cache": (CanonicalResourceType.DATABASE_CACHE, "database"),
    "azurerm_key_vault": (CanonicalResourceType.SECRETS_MANAGER, "security"),
    "azurerm_lb": (CanonicalResourceType.LOAD_BALANCER, "app"),
    "azurerm_application_gateway": (CanonicalResourceType.LOAD_BALANCER, "app"),
    "azurerm_dns_zone": (CanonicalResourceType.DNS_ZONE, "dns"),
    "azurerm_servicebus_namespace": (CanonicalResourceType.MESSAGING_TOPIC, "messaging"),
    "azurerm_eventhub_namespace": (CanonicalResourceType.MESSAGING_TOPIC, "messaging"),
}


class AzureToCanonicalMapper(BaseMapper):
    name = "azure_to_canonical"

    def supports(self, source_type: str) -> bool:
        return source_type in _AZURE_HANDLERS

    def map(self, parsed: ParsedResource) -> CanonicalResource:
        handler = _AZURE_HANDLERS.get(parsed.source_type)
        if handler is None:
            raise MappingError(f"No Azure mapping for {parsed.source_type!r}")

        canonical_type, _ = handler
        region = parsed.attributes.get("location")

        return CanonicalResource(
            id=f"azure:{parsed.source_identifier}",
            canonical_type=canonical_type,
            source_provider=CloudProvider.AZURE,
            source_type=parsed.source_type,
            name=parsed.name,
            region=str(region) if region else None,
            tags=(
                {str(k): str(v) for k, v in parsed.attributes["tags"].items()}
                if isinstance(parsed.attributes.get("tags"), dict) else {}
            ),
            depends_on=frozenset(f"azure:{d}" for d in parsed.raw_depends_on),
            native_attributes=parsed.attributes,
            source_location=SourceLocation(
                source_system="arm_template",
                source_path=parsed.source_path,
                source_identifier=parsed.source_identifier,
            ),
        )


# ---------------------------------------------------------------------------
# ServiceNow CMDB Parser
# ---------------------------------------------------------------------------


class ServiceNowCMDBParser(BaseParser):
    """Parses ServiceNow CMDB JSON export files."""

    name = "servicenow_cmdb"

    def supports(self, source_path: Path) -> bool:
        if source_path.suffix != ".json":
            return False
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
            return isinstance(data, dict) and ("result" in data or "cmdb_ci" in data)
        except Exception:
            return False

    def parse(self, source_path: Path) -> ParserResult:
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ParserError(f"Could not parse CMDB export: {source_path}", cause=exc) from exc

        items = data.get("result") or data.get("cmdb_ci") or []
        if not isinstance(items, list):
            items = [items]

        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []

        cmdb_class_map = {
            "cmdb_ci_vm_instance": "aws_instance",
            "cmdb_ci_cloud_database": "aws_db_instance",
            "cmdb_ci_cloud_load_balancer": "aws_lb",
            "cmdb_ci_cloud_storage": "aws_s3_bucket",
            "cmdb_ci_cloud_network": "aws_vpc",
            "cmdb_ci_cloud_subnet": "aws_subnet",
        }

        for item in items:
            if not isinstance(item, dict):
                continue

            ci_class = item.get("sys_class_name", "unknown")
            tf_type = cmdb_class_map.get(ci_class, ci_class)
            name = item.get("name", item.get("sys_id", "unnamed"))

            provider_str = str(item.get("cloud_provider", item.get("provider", "aws"))).lower()
            provider = CloudProvider.AWS
            if "gcp" in provider_str or "google" in provider_str:
                provider = CloudProvider.GCP
            elif "azure" in provider_str or "microsoft" in provider_str:
                provider = CloudProvider.AZURE

            resources.append(ParsedResource(
                source_provider=provider,
                source_type=tf_type,
                source_identifier=item.get("sys_id", name),
                name=str(name),
                attributes=item,
                raw_depends_on=[],
                source_path=str(source_path),
            ))

        return ParserResult(parser_name=self.name, source_path=str(source_path), resources=resources, warnings=warnings)


# ---------------------------------------------------------------------------
# Application-Centric Migration Engine
# ---------------------------------------------------------------------------


class ApplicationGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_name: str
    resource_ids: list[str] = Field(default_factory=list)
    resource_count: int = 0
    owners: list[str] = Field(default_factory=list)
    criticality: str = "unknown"
    environments: list[str] = Field(default_factory=list)


class ApplicationMigrationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applications: list[ApplicationGroup] = Field(default_factory=list)
    ungrouped_resources: list[str] = Field(default_factory=list)
    migration_order: list[str] = Field(
        default_factory=list,
        description="Application names in recommended migration order",
    )


@dataclass(slots=True)
class ApplicationCentricMigration:
    """Groups resources by application and plans application-level migration waves."""

    def analyze(self, graph: CanonicalInfrastructureGraph) -> ApplicationMigrationPlan:
        app_groups: dict[str, list[str]] = defaultdict(list)
        app_metadata: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"owners": set(), "envs": set(), "crit": set()})
        ungrouped: list[str] = []

        for resource in graph.resources.values():
            app = (
                resource.application
                or resource.tags.get("Application")
                or resource.tags.get("app")
                or resource.tags.get("Service")
                or resource.tags.get("service")
            )
            if app:
                app_groups[app].append(resource.id)
                if resource.owner:
                    app_metadata[app]["owners"].add(resource.owner)
                if resource.environment:
                    app_metadata[app]["envs"].add(resource.environment)
                if resource.criticality:
                    app_metadata[app]["crit"].add(resource.criticality)
            else:
                ungrouped.append(resource.id)

        applications: list[ApplicationGroup] = []
        for app_name, resource_ids in sorted(app_groups.items()):
            meta = app_metadata[app_name]
            crits = meta["crit"]
            # Highest criticality wins
            crit = "critical" if "critical" in crits else "high" if "high" in crits else "medium" if "medium" in crits else "low"

            applications.append(ApplicationGroup(
                application_name=app_name,
                resource_ids=resource_ids,
                resource_count=len(resource_ids),
                owners=sorted(meta["owners"]),
                criticality=crit,
                environments=sorted(meta["envs"]),
            ))

        # Migration order: low-criticality first (canary), critical last
        crit_order = {"low": 0, "medium": 1, "high": 2, "critical": 3, "unknown": 1}
        migration_order = sorted(applications, key=lambda a: crit_order.get(a.criticality, 1))

        return ApplicationMigrationPlan(
            applications=applications,
            ungrouped_resources=ungrouped,
            migration_order=[a.application_name for a in migration_order],
        )
