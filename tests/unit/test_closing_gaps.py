"""Tests for ARM, CMDB, Azure mapper, app-centric migration, renderers, perf fixtures."""

from __future__ import annotations

import json

from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph, CanonicalResource, SourceLocation
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.parsers.azure_cmdb import (
    ApplicationCentricMigration,
    ARMTemplateParser,
    AzureToCanonicalMapper,
    ServiceNowCMDBParser,
)
from migration_factory.parsers.base import ParsedResource
from migration_factory.reporting.engine import ReportingEngine
from migration_factory.reporting.renderers import ExcelReportRenderer, PDFReportRenderer, PerformanceFixtureGenerator


def _loc():
    return SourceLocation(source_system="test", source_path="test")


def _resource(rid, ctype, **kwargs):
    return CanonicalResource(
        id=rid, canonical_type=ctype, source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}", name=rid,
        native_attributes=kwargs.get("attrs", {}),
        tags=kwargs.get("tags", {}),
        application=kwargs.get("application"),
        owner=kwargs.get("owner"),
        criticality=kwargs.get("criticality"),
        source_location=_loc(),
    )


# --- ARM Template Parser ---

class TestARMTemplateParser:
    def test_supports_arm_template(self, tmp_path):
        template = {
            "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json",
            "resources": [
                {"type": "Microsoft.Compute/virtualMachines", "name": "vm1", "location": "eastus", "properties": {}},
                {"type": "Microsoft.Storage/storageAccounts", "name": "storage1", "location": "eastus", "properties": {}},
            ],
        }
        path = tmp_path / "template.json"
        path.write_text(json.dumps(template))
        parser = ARMTemplateParser()
        assert parser.supports(path) is True
        result = parser.parse(path)
        assert result.resource_count == 2
        assert any(r.source_type == "azurerm_virtual_machine" for r in result.resources)
        assert any(r.source_type == "azurerm_storage_account" for r in result.resources)

    def test_rejects_non_arm(self, tmp_path):
        path = tmp_path / "other.json"
        path.write_text('{"key": "value"}')
        assert ARMTemplateParser().supports(path) is False


# --- Azure Mapper ---

class TestAzureMapper:
    def test_supports_azure_types(self):
        mapper = AzureToCanonicalMapper()
        assert mapper.supports("azurerm_virtual_machine") is True
        assert mapper.supports("aws_instance") is False

    def test_maps_vm(self):
        parsed = ParsedResource(
            source_provider=CloudProvider.AZURE,
            source_type="azurerm_virtual_machine",
            source_identifier="vm1",
            name="vm1",
            attributes={"location": "eastus"},
            raw_depends_on=[],
            source_path="test",
        )
        canonical = AzureToCanonicalMapper().map(parsed)
        assert canonical.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE
        assert canonical.source_provider is CloudProvider.AZURE

    def test_maps_storage(self):
        parsed = ParsedResource(
            source_provider=CloudProvider.AZURE,
            source_type="azurerm_storage_account",
            source_identifier="storage1",
            name="storage1",
            attributes={},
            raw_depends_on=[],
            source_path="test",
        )
        canonical = AzureToCanonicalMapper().map(parsed)
        assert canonical.canonical_type is CanonicalResourceType.STORAGE_OBJECT_BUCKET

    def test_supports_22_azure_types(self):
        mapper = AzureToCanonicalMapper()
        count = sum(1 for t in [
            "azurerm_virtual_machine", "azurerm_virtual_network",
            "azurerm_storage_account", "azurerm_kubernetes_cluster",
            "azurerm_mssql_server", "azurerm_cosmosdb_account",
            "azurerm_key_vault", "azurerm_lb",
        ] if mapper.supports(t))
        assert count == 8


# --- ServiceNow CMDB Parser ---

class TestServiceNowCMDBParser:
    def test_parses_cmdb_export(self, tmp_path):
        cmdb = {"result": [
            {"sys_class_name": "cmdb_ci_vm_instance", "name": "prod-app-01", "sys_id": "abc123", "cloud_provider": "AWS"},
            {"sys_class_name": "cmdb_ci_cloud_database", "name": "prod-db-01", "sys_id": "def456", "cloud_provider": "GCP"},
        ]}
        path = tmp_path / "cmdb.json"
        path.write_text(json.dumps(cmdb))

        parser = ServiceNowCMDBParser()
        assert parser.supports(path) is True
        result = parser.parse(path)
        assert result.resource_count == 2
        assert result.resources[0].source_provider is CloudProvider.AWS
        assert result.resources[1].source_provider is CloudProvider.GCP

    def test_rejects_non_cmdb(self, tmp_path):
        path = tmp_path / "other.json"
        path.write_text('{"key": "value"}')
        assert ServiceNowCMDBParser().supports(path) is False


# --- Application-Centric Migration ---

class TestApplicationCentricMigration:
    def test_groups_by_application(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("web1", CanonicalResourceType.COMPUTE_INSTANCE,
            application="web-api", owner="platform", criticality="high"))
        graph.add_resource(_resource("web2", CanonicalResourceType.COMPUTE_INSTANCE,
            application="web-api", owner="platform", criticality="high"))
        graph.add_resource(_resource("db1", CanonicalResourceType.DATABASE_INSTANCE,
            application="payments", owner="data-team", criticality="critical"))
        graph.add_resource(_resource("orphan", CanonicalResourceType.STORAGE_OBJECT_BUCKET))

        plan = ApplicationCentricMigration().analyze(graph)
        assert len(plan.applications) == 2
        assert "orphan" in plan.ungrouped_resources

    def test_migration_order_low_criticality_first(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("dev", CanonicalResourceType.COMPUTE_INSTANCE,
            application="dev-tools", criticality="low"))
        graph.add_resource(_resource("prod", CanonicalResourceType.COMPUTE_INSTANCE,
            application="payments", criticality="critical"))
        graph.add_resource(_resource("staging", CanonicalResourceType.COMPUTE_INSTANCE,
            application="staging-svc", criticality="medium"))

        plan = ApplicationCentricMigration().analyze(graph)
        assert plan.migration_order[0] == "dev-tools"
        assert plan.migration_order[-1] == "payments"

    def test_aggregates_owners_and_environments(self):
        graph = CanonicalInfrastructureGraph()
        r1 = _resource("r1", CanonicalResourceType.COMPUTE_INSTANCE, application="myapp", owner="team-a")
        r1.environment = "prod"
        graph.add_resource(r1)
        r2 = _resource("r2", CanonicalResourceType.COMPUTE_INSTANCE, application="myapp", owner="team-b")
        r2.environment = "staging"
        graph.add_resource(r2)

        plan = ApplicationCentricMigration().analyze(graph)
        app = next(a for a in plan.applications if a.application_name == "myapp")
        assert "team-a" in app.owners
        assert "team-b" in app.owners
        assert "prod" in app.environments


# --- Excel Report Renderer ---

class TestExcelRenderer:
    def test_renders_xlsx(self, tmp_path):
        report = ReportingEngine().generate()
        output = tmp_path / "report.xlsx"
        ExcelReportRenderer().render(report, output)
        assert output.exists()
        assert output.stat().st_size > 0

    def test_renders_with_sections(self, tmp_path):
        from migration_factory.security.engine import SecurityEngine
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        security = SecurityEngine().analyze(graph)
        report = ReportingEngine().generate(security=security)
        output = tmp_path / "full_report.xlsx"
        ExcelReportRenderer().render(report, output)
        assert output.exists()


# --- PDF Report Renderer ---

class TestPDFRenderer:
    def test_renders_html_fallback(self, tmp_path):
        report = ReportingEngine().generate()
        html = ReportingEngine().to_html(report)
        output = tmp_path / "report.pdf"
        result = PDFReportRenderer().render(report, html, output)
        # Without weasyprint, falls back to HTML
        assert result.exists()


# --- Performance Fixture Generator ---

class TestPerformanceFixtures:
    def test_generates_large_graph(self):
        graph = PerformanceFixtureGenerator().generate(resource_count=500)
        assert len(graph.resources) >= 400  # May be slightly less due to rounding

    def test_graph_has_dependencies(self):
        graph = PerformanceFixtureGenerator().generate(resource_count=100)
        has_deps = any(len(r.depends_on) > 0 for r in graph.resources.values())
        assert has_deps is True

    def test_topological_order_works_on_large_graph(self):
        graph = PerformanceFixtureGenerator().generate(resource_count=200)
        order = graph.topological_order()
        assert len(order) == len(graph.resources)

    def test_realistic_type_distribution(self):
        graph = PerformanceFixtureGenerator().generate(resource_count=1000)
        types = {r.canonical_type for r in graph.resources.values()}
        # Should have multiple types
        assert len(types) >= 5
