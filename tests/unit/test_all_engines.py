"""Tests for all new engines: Policy, Security, Compliance, FinOps,
Validation, Terraform Generation, and Reporting.
"""

from __future__ import annotations

from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.compliance.engine import ComplianceEngine
from migration_factory.core.config import Settings
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
    SourceLocation,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.finops.engine import FinOpsEngine
from migration_factory.pipeline import IngestionPipeline
from migration_factory.policy.engine import PolicyEngine
from migration_factory.policy.models import PolicyStatus
from migration_factory.reporting.engine import ReportingEngine
from migration_factory.security.engine import SecurityEngine
from migration_factory.terraform_gen.engine import TerraformGenerator
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
from migration_factory.validation.engine import ValidationEngine


def _loc():
    return SourceLocation(source_system="test", source_path="test")


def _resource(rid, ctype, depends_on=frozenset(), **attrs):
    return CanonicalResource(
        id=rid,
        canonical_type=ctype,
        source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}",
        name=rid,
        depends_on=depends_on,
        native_attributes=attrs,
        source_location=_loc(),
    )


def _sample_graph():
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC,
        cidr_block="10.0.0.0/16", tags={"Name": "main"}))
    graph.add_resource(_resource("subnet", CanonicalResourceType.NETWORK_SUBNET,
        depends_on=frozenset({"vpc"}), availability_zone="us-east-1a", cidr_block="10.0.1.0/24"))
    graph.add_resource(_resource("sg", CanonicalResourceType.NETWORK_FIREWALL_RULE,
        depends_on=frozenset({"vpc"}), description="app sg"))
    graph.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE,
        depends_on=frozenset({"subnet", "sg"}),
        instance_type="t3.medium", availability_zone="us-east-1a",
        tags={"Name": "app", "Environment": "prod"}))
    graph.add_resource(_resource("bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET,
        region="us-east-1"))
    graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE,
        name="app-role"))
    return graph


# --- Policy Engine Tests ---

class TestPolicyEngine:
    def test_evaluate_returns_findings_for_all_resources(self):
        graph = _sample_graph()
        report = PolicyEngine().evaluate(graph)
        assert len(report.findings) > 0
        assert all(isinstance(f.status, PolicyStatus) for f in report.findings)

    def test_required_tags_fails_when_missing(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        report = PolicyEngine(parameters={"required_tags": ["Environment", "Owner"]}).evaluate(graph)
        tag_findings = [f for f in report.findings if f.check_id == "tags.required"]
        assert any(f.status is PolicyStatus.FAIL for f in tag_findings)

    def test_required_tags_passes_when_present(self):
        graph = CanonicalInfrastructureGraph()
        r = _resource("vpc", CanonicalResourceType.NETWORK_VPC)
        r.tags = {"Environment": "prod", "Owner": "platform"}
        graph.add_resource(r)
        report = PolicyEngine(parameters={"required_tags": ["Environment", "Owner"]}).evaluate(graph)
        tag_findings = [f for f in report.findings if f.check_id == "tags.required"]
        assert all(f.status is PolicyStatus.PASS for f in tag_findings)

    def test_allowed_regions_fails_for_wrong_region(self):
        graph = CanonicalInfrastructureGraph()
        r = _resource("subnet", CanonicalResourceType.NETWORK_SUBNET,
                       availability_zone="ap-southeast-1a")
        r.region = "ap-southeast-1"
        graph.add_resource(r)
        report = PolicyEngine(parameters={"allowed_regions": ["us-east-1", "us-west-2"]}).evaluate(graph)
        region_findings = [f for f in report.findings if f.check_id == "region.allowed"]
        assert any(f.status is PolicyStatus.FAIL for f in region_findings)

    def test_compliance_score_computed(self):
        graph = _sample_graph()
        report = PolicyEngine().evaluate(graph)
        assert 0 <= report.compliance_score <= 100

    def test_by_category_groups_findings(self):
        graph = _sample_graph()
        report = PolicyEngine().evaluate(graph)
        categories = report.by_category()
        assert len(categories) > 0

    def test_by_framework_filters_correctly(self):
        graph = _sample_graph()
        report = PolicyEngine().evaluate(graph)
        cis_findings = report.by_framework("CIS")
        for f in cis_findings:
            assert "CIS" in f.frameworks


# --- Security Engine Tests ---

class TestSecurityEngine:
    def test_security_analysis_produces_report(self):
        graph = _sample_graph()
        report = SecurityEngine().analyze(graph)
        assert 0 <= report.security_score <= 100
        assert report.risk_level is not None

    def test_secret_detection_finds_patterns(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE,
            password="SuperSecret123!", api_key="AKIAIOSFODNN7EXAMPLE"))
        report = SecurityEngine().analyze(graph)
        assert len(report.secret_findings) > 0

    def test_firewall_detects_open_all(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("sg", CanonicalResourceType.NETWORK_FIREWALL_RULE,
            ingress=[{"cidr_blocks": ["0.0.0.0/0"], "from_port": 0, "to_port": 65535}]))
        report = SecurityEngine().analyze(graph)
        assert any(f.finding_type == "open_all_ports" for f in report.firewall_findings)

    def test_firewall_detects_ssh_open(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("sg", CanonicalResourceType.NETWORK_FIREWALL_RULE,
            ingress=[{"cidr_blocks": ["0.0.0.0/0"], "from_port": 22, "to_port": 22}]))
        report = SecurityEngine().analyze(graph)
        assert any(f.finding_type == "ssh_open_to_world" for f in report.firewall_findings)

    def test_iam_detects_admin_access(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE,
            managed_policy_arns=["arn:aws:iam::aws:policy/AdministratorAccess"]))
        report = SecurityEngine().analyze(graph)
        assert any(f.finding_type == "admin_access" for f in report.iam_findings)


# --- Compliance Engine Tests ---

class TestComplianceEngine:
    def test_evaluates_all_frameworks(self):
        graph = _sample_graph()
        report = ComplianceEngine().evaluate(graph)
        assert len(report.framework_results) == 6
        assert 0 <= report.overall_compliance_score <= 100

    def test_compliant_vs_noncompliant_lists(self):
        graph = _sample_graph()
        report = ComplianceEngine().evaluate(graph)
        total = len(report.compliant_frameworks) + len(report.non_compliant_frameworks)
        assert total == len(report.framework_results)

    def test_per_framework_score(self):
        graph = _sample_graph()
        report = ComplianceEngine().evaluate(graph)
        for fr in report.framework_results:
            assert 0 <= fr.compliance_score <= 100


# --- FinOps Engine Tests ---

class TestFinOpsEngine:
    def test_cost_analysis_produces_summary(self):
        graph = _sample_graph()
        report = FinOpsEngine().analyze(graph)
        assert report.cost_summary.source_monthly_total > 0
        assert report.cost_summary.target_monthly_total > 0
        assert len(report.resource_estimates) == 6

    def test_savings_recommendations_generated(self):
        graph = _sample_graph()
        report = FinOpsEngine().analyze(graph)
        assert len(report.savings_recommendations) > 0

    def test_break_even_calculated(self):
        graph = _sample_graph()
        report = FinOpsEngine().analyze(graph)
        assert report.cost_summary.break_even_months >= 0

    def test_idle_detection(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("stopped", CanonicalResourceType.COMPUTE_INSTANCE,
            instance_state={"name": "stopped"}))
        report = FinOpsEngine().analyze(graph)
        assert report.cost_summary.idle_resource_count == 1


# --- Validation Engine Tests ---

class TestValidationEngine:
    def test_validates_sample_graph(self):
        graph = _sample_graph()
        report = ValidationEngine().validate(graph)
        assert report.is_valid  # sample graph should be clean

    def test_detects_invalid_cidr(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("subnet", CanonicalResourceType.NETWORK_SUBNET,
            cidr_block="999.999.999.999/33"))
        report = ValidationEngine().validate(graph)
        assert any(f.check == "cidr.invalid" for f in report.findings)

    def test_detects_dangling_dependencies(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE,
            depends_on=frozenset({"missing_vpc"}), instance_type="t3.medium"))
        report = ValidationEngine().validate(graph)
        assert any(f.check == "dependency.dangling" for f in report.findings)

    def test_detects_missing_instance_type(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE))
        report = ValidationEngine().validate(graph)
        assert any(f.check == "config.missing_instance_type" for f in report.findings)

    def test_warns_on_large_cidr(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC,
            cidr_block="10.0.0.0/8"))
        report = ValidationEngine().validate(graph)
        assert any(f.check == "cidr.too_large" for f in report.findings)


# --- Terraform Generator Tests ---

class TestTerraformGenerator:
    def test_generates_gcp_terraform_files(self):
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        graph = _sample_graph()
        translation = TranslationEngine(matrix=matrix).translate(graph)
        gen = TerraformGenerator()
        report = gen.generate(graph, translation)
        assert report.generated_resources >= 4
        filenames = {f.filename for f in report.files}
        assert "main.tf" in filenames
        assert "variables.tf" in filenames
        assert "providers.tf" in filenames
        assert "backend.tf" in filenames
        assert "versions.tf" in filenames

    def test_main_tf_contains_google_resources(self):
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        graph = _sample_graph()
        translation = TranslationEngine(matrix=matrix).translate(graph)
        gen = TerraformGenerator()
        report = gen.generate(graph, translation)
        main_tf = next(f for f in report.files if f.filename == "main.tf")
        assert "google_compute_network" in main_tf.content
        assert "google_compute_instance" in main_tf.content

    def test_writes_files_to_disk(self, tmp_path):
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        graph = _sample_graph()
        translation = TranslationEngine(matrix=matrix).translate(graph)
        gen = TerraformGenerator()
        report = gen.generate(graph, translation)
        gen.write(report, tmp_path / "output")
        assert (tmp_path / "output" / "main.tf").exists()
        assert (tmp_path / "output" / "providers.tf").exists()


# --- Reporting Engine Tests ---

class TestReportingEngine:
    def test_full_report_generation(self):
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        graph = _sample_graph()
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        security = SecurityEngine().analyze(graph)
        compliance = ComplianceEngine().evaluate(graph)
        finops = FinOpsEngine().analyze(graph)
        validation = ValidationEngine().validate(graph)
        terraform = TerraformGenerator().generate(graph, translation)

        report = ReportingEngine().generate(
            assessment=assessment,
            translation=translation,
            security=security,
            compliance=compliance,
            finops=finops,
            validation=validation,
            terraform=terraform,
        )

        md = report.to_markdown()
        assert "Executive summary" in md
        assert "Migration assessment" in md
        assert "Security analysis" in md
        assert "Compliance assessment" in md
        assert "FinOps analysis" in md
        assert "Terraform generation" in md

    def test_report_to_json_is_valid(self):
        _sample_graph()
        report = ReportingEngine().generate()
        import json
        parsed = json.loads(report.to_json())
        assert "sections" in parsed

    def test_partial_report_works(self):
        graph = _sample_graph()
        security = SecurityEngine().analyze(graph)
        report = ReportingEngine().generate(security=security)
        md = report.to_markdown()
        assert "Security analysis" in md


# --- Full Pipeline Integration ---

class TestFullPipelineIntegration:
    def test_complete_pipeline_all_engines(self, sample_tfstate_path):
        """The single test that proves the ENTIRE platform works end-to-end."""
        # Ingest
        pipeline = IngestionPipeline(settings=Settings())
        ingestion = pipeline.run(sample_tfstate_path)
        assert len(ingestion.graph.resources) == 6

        # Translate
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(ingestion.graph)

        # Assess
        assessment = AssessmentEngine().assess(ingestion.graph, translation)
        assert assessment.overall_complexity_score > 0

        # Validate
        validation = ValidationEngine().validate(ingestion.graph)

        # Security
        security = SecurityEngine().analyze(ingestion.graph)
        assert 0 <= security.security_score <= 100

        # Compliance
        compliance = ComplianceEngine().evaluate(ingestion.graph)
        assert 0 <= compliance.overall_compliance_score <= 100

        # FinOps
        finops = FinOpsEngine().analyze(ingestion.graph)
        assert finops.cost_summary.source_monthly_total > 0

        # Policy
        policy_report = PolicyEngine(
            parameters={"required_tags": ["Environment"], "allowed_regions": ["us-east-1"]}
        ).evaluate(ingestion.graph)
        assert len(policy_report.findings) > 0

        # Terraform Generation
        terraform = TerraformGenerator().generate(ingestion.graph, translation)
        assert terraform.generated_resources >= 4

        # Reporting
        report = ReportingEngine().generate(
            assessment=assessment,
            translation=translation,
            security=security,
            compliance=compliance,
            finops=finops,
            validation=validation,
            terraform=terraform,
        )
        md = report.to_markdown()
        assert len(md) > 500
        assert "Executive summary" in md
