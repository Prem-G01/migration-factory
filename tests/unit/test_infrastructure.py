"""Tests for cloud discovery, deployment, drift detection, workflow, and metrics."""

from __future__ import annotations

from migration_factory.deployment.engine import (
    DeploymentPackageGenerator,
    HealthCheckEngine,
    TerraformOrchestrator,
)
from migration_factory.discovery.providers.cloud import AWSDiscovery, GCPDiscovery
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph, CanonicalResource, SourceLocation
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.drift.engine import DriftDetectionEngine, StateReconciliationEngine
from migration_factory.metrics.collector import MetricsCollector
from migration_factory.workflow.engine import (
    PREDEFINED_WORKFLOWS,
    StageStatus,
    WorkflowEngine,
)


def _loc():
    return SourceLocation(source_system="test", source_path="test")


def _resource(rid, ctype, **attrs):
    return CanonicalResource(
        id=rid, canonical_type=ctype, source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}", name=rid,
        native_attributes=attrs, source_location=_loc(),
    )


# --- Cloud Discovery ---

class TestAWSDiscovery:
    def test_simulation_returns_resources(self):
        discovery = AWSDiscovery(simulation=True)
        result = discovery.discover(regions=["us-east-1"])
        assert result.mode == "simulation"
        assert len(result.resources) >= 5

    def test_to_parsed_resources(self):
        discovery = AWSDiscovery(simulation=True)
        result = discovery.discover()
        parsed = discovery.to_parsed_resources(result)
        assert len(parsed) >= 5
        assert all(p.source_provider is CloudProvider.AWS for p in parsed)

    def test_simulation_has_expected_types(self):
        result = AWSDiscovery(simulation=True).discover()
        types = {r.resource_type for r in result.resources}
        assert "aws_vpc" in types
        assert "aws_instance" in types


class TestGCPDiscovery:
    def test_simulation_returns_resources(self):
        discovery = GCPDiscovery(simulation=True)
        result = discovery.discover(regions=["us-central1"])
        assert result.mode == "simulation"
        assert len(result.resources) >= 4

    def test_to_parsed_resources(self):
        discovery = GCPDiscovery(simulation=True)
        result = discovery.discover()
        parsed = discovery.to_parsed_resources(result)
        assert all(p.source_provider is CloudProvider.GCP for p in parsed)


# --- Deployment Engine ---

class TestTerraformOrchestrator:
    def test_simulation_validate(self):
        orch = TerraformOrchestrator(simulation=True)
        result = orch.validate()
        assert result.success is True
        assert result.simulated is True

    def test_simulation_plan(self):
        orch = TerraformOrchestrator(simulation=True)
        result, plan = orch.plan()
        assert result.success is True
        assert "Plan" in result.stdout

    def test_simulation_apply(self):
        orch = TerraformOrchestrator(simulation=True)
        result = orch.apply()
        assert result.success is True

    def test_simulation_destroy(self):
        orch = TerraformOrchestrator(simulation=True)
        result = orch.destroy()
        assert result.success is True

    def test_simulation_fmt(self):
        result = TerraformOrchestrator(simulation=True).fmt()
        assert result.success is True


class TestDeploymentPackageGenerator:
    def test_generates_package(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "main.tf").write_text('resource "google_compute_network" "main" {}')
        (source / "variables.tf").write_text('variable "project_id" {}')

        output = tmp_path / "output"
        pkg_dir = DeploymentPackageGenerator().generate(source, output, "staging")

        assert pkg_dir.exists()
        assert (pkg_dir / "main.tf").exists()
        assert (pkg_dir / "deploy.sh").exists()
        assert (pkg_dir / "rollback.sh").exists()


class TestHealthCheckEngine:
    def test_health_checks_pass_in_simulation(self):
        orch = TerraformOrchestrator(simulation=True)
        report = HealthCheckEngine().check(orch)
        assert report.all_passed is True
        assert len(report.checks) >= 3


# --- Drift Detection ---

class TestDriftDetection:
    def test_detects_missing_resources(self):
        desired = CanonicalInfrastructureGraph()
        desired.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        desired.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE))
        actual = CanonicalInfrastructureGraph()
        actual.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))

        report = DriftDetectionEngine().detect(desired, actual)
        assert report.drift_detected is True
        assert report.missing_count == 1

    def test_detects_orphan_resources(self):
        desired = CanonicalInfrastructureGraph()
        desired.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        actual = CanonicalInfrastructureGraph()
        actual.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        actual.add_resource(_resource("orphan", CanonicalResourceType.COMPUTE_INSTANCE))

        report = DriftDetectionEngine().detect(desired, actual)
        assert report.orphan_count == 1

    def test_detects_modified_resources(self):
        desired = CanonicalInfrastructureGraph()
        desired.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        r = _resource("vpc", CanonicalResourceType.NETWORK_VPC)
        r.tags = {"changed": "true"}
        actual = CanonicalInfrastructureGraph()
        actual.add_resource(r)

        report = DriftDetectionEngine().detect(desired, actual)
        assert report.modified_count == 1

    def test_no_drift_when_identical(self):
        g1 = CanonicalInfrastructureGraph()
        g1.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        g2 = CanonicalInfrastructureGraph()
        g2.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))

        report = DriftDetectionEngine().detect(g1, g2)
        assert report.drift_detected is False
        assert report.match_count == 1


class TestStateReconciliation:
    def test_generates_reconciliation_plan(self):
        desired = CanonicalInfrastructureGraph()
        desired.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        desired.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE))
        actual = CanonicalInfrastructureGraph()
        actual.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        actual.add_resource(_resource("orphan", CanonicalResourceType.STORAGE_OBJECT_BUCKET))

        drift = DriftDetectionEngine().detect(desired, actual)
        plan = StateReconciliationEngine().reconcile(drift)

        assert plan.total_actions == 2  # 1 create + 1 import
        actions = {a.action for a in plan.actions}
        assert "create" in actions
        assert "import" in actions
        assert len(plan.import_commands) == 1


# --- Workflow Engine ---

class TestWorkflowEngine:
    def test_executes_workflow(self):
        engine = WorkflowEngine()
        engine.register_stage("step1", lambda ctx: {"result1": "done"})
        engine.register_stage("step2", lambda ctx: {"result2": ctx.get("result1", "")})

        from migration_factory.workflow.engine import WorkflowDefinition
        workflow = WorkflowDefinition(name="test", stages=["step1", "step2"])
        report = engine.execute(workflow)

        assert report.status is StageStatus.COMPLETED
        assert report.completed_stages == 2

    def test_skips_missing_handlers(self):
        engine = WorkflowEngine()
        from migration_factory.workflow.engine import WorkflowDefinition
        workflow = WorkflowDefinition(name="test", stages=["missing_stage"])
        report = engine.execute(workflow)
        assert report.stage_results[0].status is StageStatus.SKIPPED

    def test_fails_on_required_stage_error(self):
        engine = WorkflowEngine()
        engine.register_stage("critical", lambda ctx: 1 / 0)

        from migration_factory.workflow.engine import WorkflowDefinition
        workflow = WorkflowDefinition(name="test", stages=["critical"], required_stages=["critical"])
        report = engine.execute(workflow)
        assert report.status is StageStatus.FAILED

    def test_continues_on_optional_stage_error(self):
        engine = WorkflowEngine()
        engine.register_stage("optional", lambda ctx: 1 / 0)
        engine.register_stage("next", lambda ctx: {"ok": True})

        from migration_factory.workflow.engine import WorkflowDefinition
        workflow = WorkflowDefinition(name="test", stages=["optional", "next"])
        report = engine.execute(workflow)
        assert report.status is StageStatus.COMPLETED
        assert report.completed_stages == 1
        assert report.failed_stages == 1

    def test_skip_stages(self):
        engine = WorkflowEngine()
        engine.register_stage("a", lambda ctx: {"a": True})
        engine.register_stage("b", lambda ctx: {"b": True})

        from migration_factory.workflow.engine import WorkflowDefinition
        workflow = WorkflowDefinition(name="test", stages=["a", "b"])
        report = engine.execute(workflow, skip_stages={"b"})
        assert report.completed_stages == 1

    def test_predefined_workflows_exist(self):
        assert len(PREDEFINED_WORKFLOWS) >= 7
        assert "migration" in PREDEFINED_WORKFLOWS
        assert "security" in PREDEFINED_WORKFLOWS
        assert "discovery" in PREDEFINED_WORKFLOWS


# --- Metrics ---

class TestMetrics:
    def test_counter(self):
        m = MetricsCollector()
        m.increment("requests_total", 1)
        m.increment("requests_total", 1)
        summary = m.get_summary()
        assert summary.counters["requests_total"] == 2

    def test_gauge(self):
        m = MetricsCollector()
        m.gauge("cpu_usage", 45.2)
        m.gauge("cpu_usage", 50.1)
        assert m.get_summary().gauges["cpu_usage"] == 50.1

    def test_histogram(self):
        m = MetricsCollector()
        m.histogram("request_duration", 0.1)
        m.histogram("request_duration", 0.5)
        assert len(m.get_summary().histograms["request_duration"]) == 2

    def test_reset(self):
        m = MetricsCollector()
        m.increment("x")
        m.reset()
        assert m.get_summary().total_metrics == 0
