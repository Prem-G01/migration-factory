"""Tests for the final cloud ops, chat interface, and smoke test modules."""

from __future__ import annotations

from migration_factory.ai.chat import AIChatInterface, SmokeTestRunner
from migration_factory.deployment.cloud_ops import (
    ConnectivityTester,
    OTLPExporter,
    QuotaValidator,
    SecretsManager,
    TerraformLinter,
)
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph, CanonicalResource, SourceLocation
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider


def _loc():
    return SourceLocation(source_system="test", source_path="test")


def _resource(rid, ctype):
    return CanonicalResource(
        id=rid, canonical_type=ctype, source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}", name=rid,
        source_location=_loc(),
    )


def _sample_graph():
    g = CanonicalInfrastructureGraph()
    g.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
    g.add_resource(CanonicalResource(
        id="subnet", canonical_type=CanonicalResourceType.NETWORK_SUBNET,
        source_provider=CloudProvider.AWS, source_type="aws_network_subnet",
        name="subnet", depends_on=frozenset({"vpc"}), source_location=_loc(),
    ))
    g.add_resource(CanonicalResource(
        id="instance", canonical_type=CanonicalResourceType.COMPUTE_INSTANCE,
        source_provider=CloudProvider.AWS, source_type="aws_compute_instance",
        name="instance", depends_on=frozenset({"subnet"}),
        native_attributes={"instance_type": "t3.medium"}, source_location=_loc(),
    ))
    return g


# --- Quota Validator ---

class TestQuotaValidator:
    def test_simulation_validates_quotas(self):
        validator = QuotaValidator(simulation=True)
        report = validator.validate({"compute.instance": 5, "network.vpc": 2})
        assert report.mode == "simulation"
        assert report.all_sufficient is True
        assert len(report.quota_checks) == 2
        assert len(report.api_checks) >= 5

    def test_detects_quota_exceeded(self):
        validator = QuotaValidator(simulation=True)
        report = validator.validate({"compute.instance": 999})
        exceeded = [q for q in report.quota_checks if not q.sufficient]
        assert len(exceeded) == 1

    def test_api_checks_present(self):
        validator = QuotaValidator(simulation=True)
        report = validator.validate({})
        assert len(report.api_checks) >= 5


# --- Connectivity Tester ---

class TestConnectivityTester:
    def test_simulation_all_reachable(self):
        tester = ConnectivityTester(simulation=True)
        report = tester.test([
            {"host": "10.0.1.5", "port": 443, "name": "app-lb"},
            {"host": "10.0.2.10", "port": 5432, "name": "app-db"},
        ])
        assert report.all_reachable is True
        assert len(report.checks) == 2
        assert report.mode == "simulation"


# --- tflint ---

class TestTerraformLinter:
    def test_linter_simulation_when_not_installed(self):
        linter = TerraformLinter()
        result = linter.lint()
        assert result.simulated is True or result.passed is True


# --- Secrets Manager ---

class TestSecretsManager:
    def test_simulation_finds_all_secrets(self):
        sm = SecretsManager(simulation=True)
        report = sm.check_secrets(["db_password", "api_key", "jwt_secret"])
        assert report.mode == "simulation"
        assert report.secrets_found == 3
        assert report.secrets_missing == []

    def test_simulation_reports_checked_count(self):
        sm = SecretsManager(simulation=True)
        report = sm.check_secrets(["a", "b"])
        assert report.secrets_checked == 2


# --- OTLP Exporter ---

class TestOTLPExporter:
    def test_simulation_export(self):
        exporter = OTLPExporter(simulation=True)
        result = exporter.export({"requests_total": 100, "error_count": 2})
        assert result is True


# --- AI Chat Interface ---

class TestAIChatInterface:
    def test_ask_without_context(self):
        chat = AIChatInterface()
        response = chat.ask("explain the infrastructure")
        assert "No infrastructure loaded" in response

    def test_ask_with_context(self):
        chat = AIChatInterface()
        graph = _sample_graph()
        chat.load_context(graph)
        response = chat.ask("explain this infrastructure")
        assert len(response) > 0
        assert len(chat.session.messages) == 2

    def test_architecture_query(self):
        chat = AIChatInterface()
        chat.load_context(_sample_graph())
        response = chat.ask("show me the architecture summary")
        assert len(response) > 0

    def test_session_tracks_history(self):
        chat = AIChatInterface()
        chat.load_context(_sample_graph())
        chat.ask("what is this?")
        chat.ask("tell me more")
        assert len(chat.session.messages) == 4  # 2 user + 2 assistant


# --- Smoke Test Runner ---

class TestSmokeTestRunner:
    def test_runs_all_smoke_tests(self):
        graph = _sample_graph()
        report = SmokeTestRunner().run(graph)
        assert report.total_tests >= 5
        assert report.all_passed is True

    def test_detects_empty_graph(self):
        graph = CanonicalInfrastructureGraph()
        report = SmokeTestRunner().run(graph)
        empty_test = next(t for t in report.tests if t.test_name == "graph_not_empty")
        assert empty_test.passed is False

    def test_reports_pass_fail_counts(self):
        graph = _sample_graph()
        report = SmokeTestRunner().run(graph)
        assert report.passed_count + report.failed_count == report.total_tests
