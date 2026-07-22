"""Tests for parsers, planner, events, expanded policies, reporting enhancements."""

from __future__ import annotations

import json

from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.assessment.models import BusinessImpact, ReadinessAssessment, TechnicalDebt
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph, CanonicalResource, SourceLocation
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.events.engine import Event, EventBus, EventType, NotificationChannel, NotificationEngine
from migration_factory.finops.engine import FinOpsEngine
from migration_factory.parsers.multi_format import (
    CloudFormationParser,
    CSVInventoryParser,
    JSONInventoryParser,
    TerraformPlanParser,
)
from migration_factory.planner.engine import MigrationPlanner
from migration_factory.policy.engine import PolicyEngine
from migration_factory.policy.models import PolicyStatus
from migration_factory.reporting.engine import ReportingEngine
from migration_factory.security.engine import SecurityEngine
from migration_factory.terraform_gen.engine import TerraformGenerator
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
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC, tags={"Environment": "prod"}))
    graph.add_resource(_resource("subnet", CanonicalResourceType.NETWORK_SUBNET, depends_on=frozenset({"vpc"})))
    graph.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE,
        depends_on=frozenset({"subnet"}), instance_type="t3.medium", tags={"Environment": "prod"}))
    graph.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE, depends_on=frozenset({"subnet"})))
    graph.add_resource(_resource("bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET))
    graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE))
    return graph


# --- Parser Tests ---

class TestCloudFormationParser:
    def test_supports_cfn_template(self, tmp_path):
        template = {"AWSTemplateFormatVersion": "2010-09-09", "Resources": {
            "MyVPC": {"Type": "AWS::EC2::VPC", "Properties": {"CidrBlock": "10.0.0.0/16"}},
            "MyInstance": {"Type": "AWS::EC2::Instance", "Properties": {"InstanceType": "t3.micro"}, "DependsOn": "MyVPC"},
        }}
        path = tmp_path / "stack.json"
        path.write_text(json.dumps(template))
        parser = CloudFormationParser()
        assert parser.supports(path) is True
        result = parser.parse(path)
        assert result.resource_count == 2
        assert any(r.source_type == "aws_vpc" for r in result.resources)

    def test_rejects_non_cfn_json(self, tmp_path):
        path = tmp_path / "other.json"
        path.write_text('{"key": "value"}')
        assert CloudFormationParser().supports(path) is False


class TestCSVParser:
    def test_parses_csv_inventory(self, tmp_path):
        csv_content = "type,name,id,provider,region\naws_instance,app-server,i-123,aws,us-east-1\naws_vpc,main,vpc-456,aws,us-east-1\n"
        path = tmp_path / "inventory.csv"
        path.write_text(csv_content)
        result = CSVInventoryParser().parse(path)
        assert result.resource_count == 2
        assert result.resources[0].source_type == "aws_instance"


class TestJSONInventoryParser:
    def test_parses_json_inventory(self, tmp_path):
        data = {"inventory": [
            {"type": "aws_instance", "name": "app", "id": "i-123", "provider": "aws", "attributes": {"instance_type": "t3.micro"}},
        ]}
        path = tmp_path / "inventory.json"
        path.write_text(json.dumps(data))
        parser = JSONInventoryParser()
        assert parser.supports(path) is True
        result = parser.parse(path)
        assert result.resource_count == 1


class TestTerraformPlanParser:
    def test_parses_plan_json(self, tmp_path):
        plan = {"resource_changes": [
            {"mode": "managed", "type": "aws_instance", "name": "app", "address": "aws_instance.app",
             "change": {"after": {"id": "i-new", "instance_type": "t3.medium"}}},
            {"mode": "managed", "type": "aws_vpc", "name": "main", "address": "aws_vpc.main",
             "change": {"after": {"id": "vpc-new", "cidr_block": "10.0.0.0/16"}}},
        ]}
        path = tmp_path / "plan.json"
        path.write_text(json.dumps(plan))
        parser = TerraformPlanParser()
        assert parser.supports(path) is True
        result = parser.parse(path)
        assert result.resource_count == 2


# --- Planner Tests ---

class TestMigrationPlanner:
    def test_generates_enhanced_plan(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        plan = MigrationPlanner().plan(graph, assessment, translation)

        assert len(plan.waves) > 0
        assert plan.cutover_plan.total_downtime_minutes > 0
        assert plan.maintenance_window.recommended_window_hours > 0
        assert 0 <= plan.confidence.overall_confidence <= 100
        assert len(plan.post_migration_verification) > 0

    def test_waves_have_validation_checkpoints(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        plan = MigrationPlanner().plan(graph, assessment, translation)
        for wave in plan.waves:
            assert len(wave.validation_checkpoints) > 0

    def test_confidence_score_computed(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        plan = MigrationPlanner().plan(graph, assessment, translation)
        assert len(plan.confidence.factors) > 0

    def test_cutover_plan_has_steps(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        plan = MigrationPlanner().plan(graph, assessment, translation)
        assert len(plan.cutover_plan.steps) >= 4
        assert len(plan.cutover_plan.pre_cutover_checks) > 0
        assert len(plan.cutover_plan.post_cutover_checks) > 0


# --- Event Bus Tests ---

class TestEventBus:
    def test_publish_and_subscribe(self):
        bus = EventBus()
        received = []
        bus.subscribe(EventType.PIPELINE_STARTED, lambda e: received.append(e))
        bus.publish(Event(event_type=EventType.PIPELINE_STARTED, source="test"))
        assert len(received) == 1

    def test_event_history(self):
        bus = EventBus()
        bus.publish(Event(event_type=EventType.PIPELINE_STARTED, source="test"))
        bus.publish(Event(event_type=EventType.PIPELINE_COMPLETED, source="test"))
        assert len(bus.event_history) == 2

    def test_handler_failure_doesnt_crash_bus(self):
        bus = EventBus()
        bus.subscribe(EventType.PIPELINE_STARTED, lambda e: 1 / 0)
        bus.publish(Event(event_type=EventType.PIPELINE_STARTED, source="test"))
        # Should not raise

    def test_notification_engine(self):
        engine = NotificationEngine()
        notification = engine.notify(NotificationChannel.LOG, "Test", "Body")
        assert notification.sent is True
        assert len(engine.sent_notifications) == 1


# --- Expanded Policy Tests ---

class TestExpandedPolicies:
    def test_least_privilege_detects_wildcard(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE,
            inline_policy={"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}))
        report = PolicyEngine().evaluate(graph)
        lp_findings = [f for f in report.findings if f.check_id == "iam.least_privilege" and f.status is PolicyStatus.FAIL]
        assert len(lp_findings) > 0

    def test_zero_trust_detects_open_ingress(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("sg", CanonicalResourceType.NETWORK_FIREWALL_RULE,
            ingress=[{"cidr_blocks": ["0.0.0.0/0"], "from_port": 0, "to_port": 65535}]))
        report = PolicyEngine().evaluate(graph)
        zt_findings = [f for f in report.findings if f.check_id == "security.zero_trust" and f.status is PolicyStatus.FAIL]
        assert len(zt_findings) > 0

    def test_org_hierarchy_check(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        report = PolicyEngine(parameters={"required_org_fields": ["owner", "environment"]}).evaluate(graph)
        org_findings = [f for f in report.findings if f.check_id == "org.hierarchy"]
        assert any(f.status is PolicyStatus.FAIL for f in org_findings)

    def test_all_11_checks_registered(self):
        from migration_factory.policy.engine import CHECK_IMPLEMENTATIONS
        assert len(CHECK_IMPLEMENTATIONS) == 11


# --- Reporting Enhancements ---

class TestReportingEnhancements:
    def test_html_report_generated(self):
        graph = _sample_graph()
        security = SecurityEngine().analyze(graph)
        report = ReportingEngine().generate(security=security)
        html = ReportingEngine().to_html(report)
        assert "<!DOCTYPE html>" in html
        assert "Security" in html

    def test_inventory_report(self):
        graph = _sample_graph()
        report = ReportingEngine().generate_inventory_report(graph)
        assert "inventory" in report.title.lower()
        assert len(report.sections) == 1

    def test_dedicated_security_report(self):
        graph = _sample_graph()
        security = SecurityEngine().analyze(graph)
        report = ReportingEngine().generate_security_report(security)
        assert "Security" in report.title

    def test_dedicated_finops_report(self):
        graph = _sample_graph()
        finops = FinOpsEngine().analyze(graph)
        report = ReportingEngine().generate_finops_report(finops)
        assert "FinOps" in report.title


# --- Assessment Model Enhancements ---

class TestAssessmentModels:
    def test_business_impact_model(self):
        bi = BusinessImpact(
            affected_applications=["payments-api"],
            affected_teams=["platform"],
            critical_resource_count=2,
            revenue_risk="medium",
        )
        assert bi.revenue_risk == "medium"

    def test_technical_debt_model(self):
        td = TechnicalDebt(
            issues=["No encryption at rest", "Oversized instances"],
            modernization_opportunities=["Containerize app tier"],
            debt_score=45,
        )
        assert td.debt_score == 45

    def test_readiness_assessment_model(self):
        ra = ReadinessAssessment(
            overall_readiness="partially_ready",
            checklist={"network_ready": True, "iam_ready": False, "data_sync_plan": False},
            blockers_remaining=2,
            readiness_score=60,
        )
        assert ra.readiness_score == 60


# --- GCP → AWS Matrix ---

class TestGCPToAWSMatrix:
    def test_gcp_to_aws_matrix_loads(self):
        matrix = load_builtin_matrix(CloudProvider.GCP, CloudProvider.AWS)
        assert len(matrix.rules) == 29
        assert matrix.source_provider is CloudProvider.GCP
        assert matrix.target_provider is CloudProvider.AWS


# --- Terraform Gen Enhancements ---

class TestTerraformGenEnhancements:
    def test_import_blocks_generated(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        gen = TerraformGenerator()
        imports = gen.generate_import_blocks(graph, translation)
        assert imports.filename == "imports.tf"
        assert "import" in imports.content

    def test_module_structure_generated(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        gen = TerraformGenerator()
        modules = gen.generate_module_structure(graph, translation)
        assert len(modules) > 0
        assert any("main_modular.tf" in f.filename for f in modules)
