"""Azure Live Discovery Module.

Full azure-mgmt based resource discovery. Activated by providing Azure
credentials (service principal or az login).

Required: pip install azure-mgmt-compute azure-mgmt-network
          azure-mgmt-resource azure-mgmt-storage azure-identity
Credentials: az login, or set AZURE_CLIENT_ID + AZURE_CLIENT_SECRET +
             AZURE_TENANT_ID, or managed identity when running in Azure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.base import ParsedResource

logger = get_logger(__name__)


class AzureDiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: CloudProvider = CloudProvider.AZURE
    subscription_id: str
    resources: list[ParsedResource] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    resource_counts: dict[str, int] = Field(default_factory=dict)
    mode: str = "live"


def _parsed(
    resource_type: str, resource_id: str, name: str,
    attributes: dict[str, Any], subscription: str
) -> ParsedResource:
    return ParsedResource(
        source_provider=CloudProvider.AZURE,
        source_type=resource_type,
        source_identifier=resource_id,
        name=name,
        attributes=attributes,
        raw_depends_on=[],
        source_path=f"azure_discovery:{subscription}",
    )


@dataclass(slots=True)
class AzureLiveDiscovery:
    """Full azure-mgmt based Azure resource discovery."""

    subscription_id: str = ""
    simulation: bool = False

    def _credential(self) -> Any:
        try:
            from azure.identity import DefaultAzureCredential
            return DefaultAzureCredential()
        except ImportError as exc:
            raise RuntimeError("azure-identity required: pip install azure-identity") from exc

    def discover_all(self) -> AzureDiscoveryResult:
        """Discover all resources in the configured subscription."""
        if self.simulation:
            return self._simulate()

        resources: list[ParsedResource] = []
        errors: list[str] = []
        counts: dict[str, int] = {}

        discoverers = [
            ("azurerm_virtual_network", self._discover_vnets),
            ("azurerm_virtual_machine", self._discover_vms),
            ("azurerm_storage_account", self._discover_storage),
            ("azurerm_mssql_server", self._discover_sql_servers),
            ("azurerm_kubernetes_cluster", self._discover_aks),
            ("azurerm_key_vault", self._discover_key_vaults),
            ("azurerm_lb", self._discover_load_balancers),
        ]

        for rtype, fn in discoverers:
            try:
                discovered = fn()
                resources.extend(discovered)
                counts[rtype] = len(discovered)
            except Exception as exc:
                errors.append(f"{rtype}: {exc}")
                logger.warning("azure_discovery_error", resource_type=rtype, error=str(exc))

        logger.info("azure_discovery_completed", subscription=self.subscription_id, total=len(resources))
        return AzureDiscoveryResult(
            subscription_id=self.subscription_id, resources=resources,
            errors=errors, resource_counts=counts,
        )

    def _discover_vnets(self) -> list[ParsedResource]:
        from azure.mgmt.network import NetworkManagementClient
        client = NetworkManagementClient(self._credential(), self.subscription_id)
        result = []
        for vnet in client.virtual_networks.list_all():
            addr_prefixes = vnet.address_space.address_prefixes if vnet.address_space else []
            result.append(_parsed(
                "azurerm_virtual_network", vnet.id or vnet.name or "", vnet.name or "",
                {"location": vnet.location, "address_space": addr_prefixes, "id": vnet.id},
                self.subscription_id,
            ))
        return result

    def _discover_vms(self) -> list[ParsedResource]:
        from azure.mgmt.compute import ComputeManagementClient
        client = ComputeManagementClient(self._credential(), self.subscription_id)
        return [
            _parsed("azurerm_virtual_machine", vm.id or vm.name, vm.name or "",
                    {"location": vm.location, "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else "",
                     "id": vm.id, "tags": dict(vm.tags or {})},
                    self.subscription_id)
            for vm in client.virtual_machines.list_all()
        ]

    def _discover_storage(self) -> list[ParsedResource]:
        from azure.mgmt.storage import StorageManagementClient
        client = StorageManagementClient(self._credential(), self.subscription_id)
        return [
            _parsed("azurerm_storage_account", acc.id or acc.name, acc.name or "",
                    {"location": acc.location, "sku": acc.sku.name if acc.sku else "",
                     "kind": acc.kind, "id": acc.id},
                    self.subscription_id)
            for acc in client.storage_accounts.list()
        ]

    def _discover_sql_servers(self) -> list[ParsedResource]:
        try:
            from azure.mgmt.sql import SqlManagementClient
            client = SqlManagementClient(self._credential(), self.subscription_id)
            return [
                _parsed("azurerm_mssql_server", srv.id or srv.name, srv.name or "",
                        {"location": srv.location, "fully_qualified_domain_name": srv.fully_qualified_domain_name,
                         "id": srv.id},
                        self.subscription_id)
                for srv in client.servers.list()
            ]
        except ImportError:
            return []

    def _discover_aks(self) -> list[ParsedResource]:
        try:
            from azure.mgmt.containerservice import ContainerServiceClient
            client = ContainerServiceClient(self._credential(), self.subscription_id)
            return [
                _parsed("azurerm_kubernetes_cluster", cluster.id or cluster.name, cluster.name or "",
                        {"location": cluster.location, "kubernetes_version": cluster.kubernetes_version,
                         "id": cluster.id},
                        self.subscription_id)
                for cluster in client.managed_clusters.list()
            ]
        except ImportError:
            return []

    def _discover_key_vaults(self) -> list[ParsedResource]:
        try:
            from azure.mgmt.keyvault import KeyVaultManagementClient
            client = KeyVaultManagementClient(self._credential(), self.subscription_id)
            return [
                _parsed("azurerm_key_vault", vault.id or vault.name, vault.name or "",
                        {"location": vault.location, "vault_uri": vault.properties.vault_uri if vault.properties else "",
                         "id": vault.id},
                        self.subscription_id)
                for vault in client.vaults.list()
            ]
        except ImportError:
            return []

    def _discover_load_balancers(self) -> list[ParsedResource]:
        from azure.mgmt.network import NetworkManagementClient
        client = NetworkManagementClient(self._credential(), self.subscription_id)
        return [
            _parsed("azurerm_lb", lb.id or lb.name, lb.name or "",
                    {"location": lb.location, "sku": lb.sku.name if lb.sku else "", "id": lb.id},
                    self.subscription_id)
            for lb in client.load_balancers.list_all()
        ]

    def _simulate(self) -> AzureDiscoveryResult:
        sim_resources = [
            ParsedResource(
                source_provider=CloudProvider.AZURE, source_type="azurerm_virtual_network",
                source_identifier="sim-vnet-001", name="main-vnet",
                attributes={"location": "eastus", "address_space": ["10.0.0.0/16"]},
                raw_depends_on=[], source_path="azure_simulation",
            ),
            ParsedResource(
                source_provider=CloudProvider.AZURE, source_type="azurerm_virtual_machine",
                source_identifier="sim-vm-001", name="app-vm",
                attributes={"location": "eastus", "vm_size": "Standard_D2s_v3"},
                raw_depends_on=[], source_path="azure_simulation",
            ),
            ParsedResource(
                source_provider=CloudProvider.AZURE, source_type="azurerm_storage_account",
                source_identifier="sim-storage-001", name="appstorage",
                attributes={"location": "eastus", "kind": "StorageV2"},
                raw_depends_on=[], source_path="azure_simulation",
            ),
        ]
        return AzureDiscoveryResult(
            subscription_id=self.subscription_id or "sim-subscription",
            resources=sim_resources,
            resource_counts={r.source_type: 1 for r in sim_resources},
            mode="simulation",
        )
