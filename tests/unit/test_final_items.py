"""Tests for the final 17 buildable items."""

from __future__ import annotations

from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph, CanonicalResource, SourceLocation
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.finops.extended import NetworkCostAnalyzer, StorageOptimizer
from migration_factory.mappers.gcp_to_canonical import GCPToCanonicalMapper
from migration_factory.parsers.base import ParsedResource
from migration_factory.parsers.extended import ExcelInventoryParser, TerraformHCLParser, TerraformLogParser
from migration_factory.policy.compliance_packs import CIS_POLICIES, NIST_POLICIES
from migration_factory.policy.engine import PolicyEngine
from migration_factory.terraform_gen.extended import TerraformEnvironmentGenerator, TerraformTestGenerator, format_terraform
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix


def _loc():
    return SourceLocation(source_system="test", source_path="test")


def _resource(rid, ctype, depends_on=frozenset(), tags=None, **attrs):
    return CanonicalResource(
        id=rid, canonical_type=ctype, source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}", name=rid,
        depends_on=depends_on, tags=tags or {}, native_attributes=attrs, source_location=_loc(),
    )


def _sample_graph():
    g = CanonicalInfrastructureGraph()
    g.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
    g.add_resource(_resource("subnet", CanonicalResourceType.NETWORK_SUBNET, depends_on=frozenset({"vpc"})))
    g.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE,
        depends_on=frozenset({"subnet"}), instance_type="t3.medium"))
    g.add_resource(_resource("bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET))
    g.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE, depends_on=frozenset({"subnet"})))
    g.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE))
    return g


# --- HCL Parser ---

class TestTerraformHCLParser:
    def test_supports_tf_files(self, tmp_path):
        tf = tmp_path / "main.tf"
        tf.write_text('resource "aws_instance" "app" {\n  ami = "ami-123"\n  instance_type = "t3.micro"\n}\n')
        assert TerraformHCLParser().supports(tf) is True

    def test_parses_hcl_resources(self, tmp_path):
        tf = tmp_path / "main.tf"
        hcl = (
            'resource "aws_instance" "app" {\n  ami = "ami-123"\n}\n\n'
            'resource "aws_vpc" "main" {\n  cidr_block = "10.0.0.0/16"\n}\n'
        )
        tf.write_text(hcl)
        result = TerraformHCLParser().parse(tf)
        assert result.resource_count == 2
        types = {r.source_type for r in result.resources}
        assert "aws_instance" in types
        assert "aws_vpc" in types

    def test_rejects_non_tf(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("hello")
        assert TerraformHCLParser().supports(f) is False


# --- Terraform Log Parser ---

class TestTerraformLogParser:
    def test_supports_terraform_log(self, tmp_path):
        log = tmp_path / "apply.log"
        log.write_text("Terraform v1.8.1\naws_vpc.main: Creating...\naws_vpc.main: Creation complete after 5s\nApply complete!\n")
        assert TerraformLogParser().supports(log) is True

    def test_parses_log_resources(self, tmp_path):
        log = tmp_path / "apply.log"
        log.write_text("aws_vpc.main: Creating...\naws_instance.app: Creating...\naws_instance.app: Still creating...\nApply complete!\n")
        result = TerraformLogParser().parse(log)
        assert result.resource_count == 2

    def test_rejects_non_terraform_log(self, tmp_path):
        log = tmp_path / "other.log"
        log.write_text("some random log content\nno terraform here\n")
        assert TerraformLogParser().supports(log) is False


# --- Excel Parser ---

class TestExcelParser:
    def test_parses_xlsx(self, tmp_path):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["type", "name", "id", "provider", "region"])
        ws.append(["aws_instance", "app-server", "i-123", "aws", "us-east-1"])
        ws.append(["aws_vpc", "main", "vpc-456", "aws", "us-east-1"])
        path = tmp_path / "inventory.xlsx"
        wb.save(str(path))

        result = ExcelInventoryParser().parse(path)
        assert result.resource_count == 2
        assert result.resources[0].source_type == "aws_instance"

    def test_supports_xlsx_only(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b,c")
        assert ExcelInventoryParser().supports(f) is False
        f2 = tmp_path / "data.xlsx"
        f2.write_bytes(b"")  # empty but has extension
        assert ExcelInventoryParser().supports(f2) is True


# --- GCP Mapper ---

class TestGCPMapper:
    def test_supports_google_types(self):
        mapper = GCPToCanonicalMapper()
        assert mapper.supports("google_compute_instance") is True
        assert mapper.supports("aws_instance") is False

    def test_maps_compute_instance(self):
        parsed = ParsedResource(
            source_provider=CloudProvider.GCP,
            source_type="google_compute_instance",
            source_identifier="google_compute_instance.app",
            name="app-vm",
            attributes={"zone": "us-central1-a"},
            raw_depends_on=[],
            source_path="test.tfstate",
        )
        canonical = GCPToCanonicalMapper().map(parsed)
        assert canonical.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE
        assert canonical.source_provider is CloudProvider.GCP

    def test_maps_gcs_bucket(self):
        parsed = ParsedResource(
            source_provider=CloudProvider.GCP,
            source_type="google_storage_bucket",
            source_identifier="google_storage_bucket.data",
            name="my-bucket",
            attributes={"location": "US"},
            raw_depends_on=[],
            source_path="test.tfstate",
        )
        canonical = GCPToCanonicalMapper().map(parsed)
        assert canonical.canonical_type is CanonicalResourceType.STORAGE_OBJECT_BUCKET

    def test_maps_cloud_sql(self):
        parsed = ParsedResource(
            source_provider=CloudProvider.GCP,
            source_type="google_sql_database_instance",
            source_identifier="google_sql_database_instance.db",
            name="my-db",
            attributes={"region": "us-central1"},
            raw_depends_on=[],
            source_path="test.tfstate",
        )
        canonical = GCPToCanonicalMapper().map(parsed)
        assert canonical.canonical_type is CanonicalResourceType.DATABASE_INSTANCE

    def test_supports_29_gcp_types(self):
        mapper = GCPToCanonicalMapper()
        count = sum(1 for t in [
            "google_compute_network", "google_compute_subnetwork", "google_compute_firewall",
            "google_compute_instance", "google_container_cluster", "google_storage_bucket",
            "google_sql_database_instance", "google_service_account", "google_pubsub_topic",
        ] if mapper.supports(t))
        assert count == 9  # spot check


# --- TF Environment Generator ---

class TestTerraformEnvironmentGenerator:
    def test_generates_env_tfvars(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        files = TerraformEnvironmentGenerator().generate(graph, translation)
        filenames = {f.filename for f in files}
        assert "environments/dev.tfvars" in filenames
        assert "environments/staging.tfvars" in filenames
        assert "environments/prod.tfvars" in filenames
        assert "environments/README.md" in filenames


# --- TF Test Generator ---

class TestTerraformTestGenerator:
    def test_generates_test_file(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        files = TerraformTestGenerator().generate(graph, translation)
        assert len(files) == 1
        assert files[0].filename == "tests/main.tftest.hcl"
        assert "validate_plan" in files[0].content
        assert "assert" in files[0].content


# --- TF Formatter ---

class TestTerraformFormatter:
    def test_formats_hcl(self):
        ugly = 'resource "aws_instance" "app" {\nami = "ami-123"\ntags = {\nName = "app"\n}\n}'
        formatted = format_terraform(ugly)
        lines = formatted.split("\n")
        assert lines[1].startswith("  ")  # indented
        assert lines[3].startswith("    ")  # double indented


# --- Network Cost Analyzer ---

class TestNetworkCostAnalyzer:
    def test_estimates_transfer_costs(self):
        graph = _sample_graph()
        result = NetworkCostAnalyzer().analyze(graph)
        assert result.migration_transfer_gb > 0
        assert result.migration_transfer_cost > 0
        assert len(result.recommendations) > 0


# --- Storage Optimizer ---

class TestStorageOptimizer:
    def test_detects_missing_lifecycle(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET))
        result = StorageOptimizer().analyze(graph)
        assert "bucket" in result.missing_lifecycle_policy
        assert result.estimated_savings_monthly > 0

    def test_detects_standard_class(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET, storage_class="STANDARD"))
        result = StorageOptimizer().analyze(graph)
        assert len(result.wrong_storage_class) > 0


# --- CIS/NIST Policy Packs ---

class TestCompliancePacks:
    def test_cis_pack_has_rules(self):
        assert len(CIS_POLICIES) >= 6
        for p in CIS_POLICIES:
            assert "CIS" in p.frameworks

    def test_nist_pack_has_rules(self):
        assert len(NIST_POLICIES) >= 6
        for p in NIST_POLICIES:
            assert "NIST" in p.frameworks

    def test_cis_pack_evaluates(self):
        graph = _sample_graph()
        report = PolicyEngine(policies=CIS_POLICIES).evaluate(graph)
        assert len(report.findings) > 0
        cis_findings = report.by_framework("CIS")
        assert len(cis_findings) > 0

    def test_nist_pack_evaluates(self):
        graph = _sample_graph()
        report = PolicyEngine(policies=NIST_POLICIES).evaluate(graph)
        nist_findings = report.by_framework("NIST")
        assert len(nist_findings) > 0

    def test_combined_packs(self):
        from migration_factory.policy.engine import DEFAULT_POLICIES
        all_policies = DEFAULT_POLICIES + CIS_POLICIES + NIST_POLICIES
        graph = _sample_graph()
        report = PolicyEngine(policies=all_policies).evaluate(graph)
        assert len(report.findings) > len(DEFAULT_POLICIES)
