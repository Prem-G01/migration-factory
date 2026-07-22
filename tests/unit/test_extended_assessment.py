"""Tests for extended assessment: business impact, tech debt, readiness,
Mermaid diagram, and version management."""

from __future__ import annotations

from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.assessment.extended import (
    BusinessImpactAnalyzer,
    ReadinessAssessor,
    TechnicalDebtAnalyzer,
    generate_mermaid_diagram,
    get_platform_version,
)
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
    SourceLocation,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix


def _loc():
    return SourceLocation(source_system="test", source_path="test")


def _resource(rid, ctype, depends_on=frozenset(), tags=None, **attrs):
    return CanonicalResource(
        id=rid, canonical_type=ctype, source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}", name=rid,
        depends_on=depends_on, tags=tags or {}, native_attributes=attrs,
        source_location=_loc(),
        owner=attrs.pop("_owner", None),
        application=attrs.pop("_application", None),
        criticality=attrs.pop("_criticality", None),
    )


def _sample_graph():
    g = CanonicalInfrastructureGraph()
    g.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC,
        tags={"Environment": "prod"}, _owner="platform", _application="payments", _criticality="critical"))
    g.add_resource(_resource("subnet", CanonicalResourceType.NETWORK_SUBNET,
        depends_on=frozenset({"vpc"}), _owner="platform"))
    g.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE,
        depends_on=frozenset({"subnet"}), instance_type="t3.medium",
        _owner="app-team", _application="payments", _criticality="high"))
    g.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE,
        depends_on=frozenset({"subnet"}), _criticality="critical"))
    g.add_resource(_resource("bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET))
    g.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE))
    return g


class TestBusinessImpactAnalyzer:
    def test_identifies_affected_applications(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        impact = BusinessImpactAnalyzer().analyze(graph, assessment)
        assert "payments" in impact.affected_applications

    def test_identifies_affected_teams(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        impact = BusinessImpactAnalyzer().analyze(graph, assessment)
        assert "platform" in impact.affected_teams

    def test_counts_critical_resources(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        impact = BusinessImpactAnalyzer().analyze(graph, assessment)
        assert impact.critical_resource_count >= 2

    def test_revenue_risk_scales_with_criticality(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        impact = BusinessImpactAnalyzer().analyze(graph, assessment)
        assert impact.revenue_risk in {"medium", "high"}


class TestTechnicalDebtAnalyzer:
    def test_detects_missing_tags(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("bare", CanonicalResourceType.COMPUTE_INSTANCE, instance_type="t3.micro"))
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        debt = TechnicalDebtAnalyzer().analyze(graph, translation)
        assert any("no tags" in issue for issue in debt.issues)

    def test_identifies_modernization_opportunities(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        debt = TechnicalDebtAnalyzer().analyze(graph, translation)
        assert len(debt.modernization_opportunities) > 0

    def test_debt_score_computed(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        debt = TechnicalDebtAnalyzer().analyze(graph, translation)
        assert 0 <= debt.debt_score <= 100


class TestReadinessAssessor:
    def test_produces_readiness_assessment(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        readiness = ReadinessAssessor().assess(graph, assessment, translation)
        assert readiness.overall_readiness in {"ready", "partially_ready", "not_ready"}
        assert 0 <= readiness.readiness_score <= 100

    def test_checklist_has_all_items(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        readiness = ReadinessAssessor().assess(graph, assessment, translation)
        assert len(readiness.checklist) >= 7

    def test_blockers_remaining_counted(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        readiness = ReadinessAssessor().assess(graph, assessment, translation)
        assert readiness.blockers_remaining >= 0


class TestMermaidDiagram:
    def test_generates_valid_mermaid(self):
        graph = _sample_graph()
        mermaid = generate_mermaid_diagram(graph)
        assert mermaid.startswith("graph TD")
        assert "vpc" in mermaid
        assert "-->" in mermaid

    def test_includes_all_resources(self):
        graph = _sample_graph()
        mermaid = generate_mermaid_diagram(graph)
        for rid in graph.resources:
            safe_id = rid.replace(":", "_").replace(".", "_").replace("-", "_")
            assert safe_id in mermaid

    def test_includes_style_classes(self):
        graph = _sample_graph()
        mermaid = generate_mermaid_diagram(graph)
        assert "classDef" in mermaid


class TestVersionManagement:
    def test_version_info(self):
        v = get_platform_version()
        assert v.platform_version == "0.6.0"
        assert v.engine_count == 18
        assert v.canonical_type_count == 29
        assert v.policy_check_count == 11
        assert v.parser_count == 5
        assert "aws" in v.supported_providers
        assert "gcp" in v.supported_target_providers
