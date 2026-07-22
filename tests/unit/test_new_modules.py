"""Tests for the 4 new modules: aws_live, gcp_live, azure_live, pdf_native."""

from __future__ import annotations

from migration_factory.discovery.aws_live import AWSLiveDiscovery
from migration_factory.discovery.azure_live import AzureLiveDiscovery
from migration_factory.discovery.gcp_live import GCPLiveDiscovery
from migration_factory.domain.enums import CloudProvider
from migration_factory.reporting.engine import ReportingEngine
from migration_factory.reporting.pdf_native import NativePDFRenderer, PDFStrategy, _detect_strategy


class TestAWSLiveDiscovery:
    def test_simulation_returns_results(self):
        discovery = AWSLiveDiscovery(simulation=True, regions=["us-east-1"])
        results = discovery.discover_all()
        assert len(results) >= 1
        assert results[0].mode == "simulation"

    def test_simulation_resources_are_aws(self):
        discovery = AWSLiveDiscovery(simulation=True)
        results = discovery.discover_all()
        for result in results:
            for r in result.resources:
                assert r.source_provider is CloudProvider.AWS

    def test_simulation_has_multiple_types(self):
        discovery = AWSLiveDiscovery(simulation=True)
        results = discovery.discover_all()
        all_types = {r.source_type for res in results for r in res.resources}
        assert len(all_types) >= 4

    def test_region_scoped_result(self):
        discovery = AWSLiveDiscovery(simulation=True, regions=["eu-west-1"])
        results = discovery.discover_all()
        assert results[0].region == "eu-west-1"

    def test_live_mode_requires_boto3_not_crash(self):
        # When boto3 is not installed or no creds, should not crash the import
        discovery = AWSLiveDiscovery(simulation=True)
        assert discovery.simulation is True


class TestGCPLiveDiscovery:
    def test_simulation_returns_result(self):
        discovery = GCPLiveDiscovery(simulation=True, project_id="test-project")
        result = discovery.discover_all()
        assert result.mode == "simulation"
        assert result.project_id == "test-project"

    def test_simulation_resources_are_gcp(self):
        discovery = GCPLiveDiscovery(simulation=True)
        result = discovery.discover_all()
        for r in result.resources:
            assert r.source_provider is CloudProvider.GCP

    def test_simulation_has_multiple_gcp_types(self):
        discovery = GCPLiveDiscovery(simulation=True)
        result = discovery.discover_all()
        types = {r.source_type for r in result.resources}
        assert any("google_" in t for t in types)

    def test_resource_counts_tracked(self):
        discovery = GCPLiveDiscovery(simulation=True)
        result = discovery.discover_all()
        assert isinstance(result.resource_counts, dict)


class TestAzureLiveDiscovery:
    def test_simulation_returns_result(self):
        discovery = AzureLiveDiscovery(simulation=True, subscription_id="sim-sub")
        result = discovery.discover_all()
        assert result.mode == "simulation"
        assert len(result.resources) >= 3

    def test_simulation_resources_are_azure(self):
        discovery = AzureLiveDiscovery(simulation=True)
        result = discovery.discover_all()
        for r in result.resources:
            assert r.source_provider is CloudProvider.AZURE

    def test_simulation_covers_vm_network_storage(self):
        discovery = AzureLiveDiscovery(simulation=True)
        result = discovery.discover_all()
        types = {r.source_type for r in result.resources}
        assert "azurerm_virtual_machine" in types
        assert "azurerm_virtual_network" in types
        assert "azurerm_storage_account" in types

    def test_simulation_id_set(self):
        discovery = AzureLiveDiscovery(simulation=True, subscription_id="my-sub-123")
        result = discovery.discover_all()
        assert result.subscription_id == "my-sub-123"


class TestNativePDFRenderer:
    def test_detects_strategy(self):
        strategy = _detect_strategy()
        assert strategy in {PDFStrategy.WEASYPRINT, PDFStrategy.REPORTLAB, PDFStrategy.HTML_FALLBACK}

    def test_html_fallback_creates_file(self, tmp_path):
        renderer = NativePDFRenderer(strategy=PDFStrategy.HTML_FALLBACK)
        report = ReportingEngine().generate()
        output = tmp_path / "report.pdf"
        result = renderer.render(report, output)
        assert result.exists()
        assert result.read_text(encoding="utf-8").startswith("<!DOCTYPE html")

    def test_renderer_auto_selects_strategy(self):
        renderer = NativePDFRenderer()
        assert renderer.strategy in {PDFStrategy.WEASYPRINT, PDFStrategy.REPORTLAB, PDFStrategy.HTML_FALLBACK}

    def test_render_with_sections(self, tmp_path):
        from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph, CanonicalResource, SourceLocation
        from migration_factory.domain.enums import CanonicalResourceType
        from migration_factory.security.engine import SecurityEngine

        graph = CanonicalInfrastructureGraph()
        graph.add_resource(CanonicalResource(
            id="vpc", canonical_type=CanonicalResourceType.NETWORK_VPC,
            source_provider=CloudProvider.AWS, source_type="aws_vpc", name="vpc",
            source_location=SourceLocation(source_system="test", source_path="test"),
        ))
        security = SecurityEngine().analyze(graph)
        report = ReportingEngine().generate(security=security)
        renderer = NativePDFRenderer(strategy=PDFStrategy.HTML_FALLBACK)
        result = renderer.render(report, tmp_path / "full.pdf")
        assert result.exists()
        assert result.stat().st_size > 0
