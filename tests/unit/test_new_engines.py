"""Tests for AI Intelligence, Knowledge Graph, Rollback Planner, and Discovery Engine."""

from __future__ import annotations

from migration_factory.ai.engine import AIAnalysisType, AIEngine
from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.discovery.engine import DiscoveryEngine
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
    SourceLocation,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.knowledge_graph.engine import DependencyType, KnowledgeGraphEngine
from migration_factory.rollback.engine import RollbackPlanner
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix


def _loc():
    return SourceLocation(source_system="test", source_path="test")


def _resource(rid, ctype, depends_on=frozenset(), tags=None, **attrs):
    return CanonicalResource(
        id=rid,
        canonical_type=ctype,
        source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}",
        name=rid,
        depends_on=depends_on,
        tags=tags or {},
        native_attributes=attrs,
        source_location=_loc(),
    )


def _sample_graph():
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC,
        tags={"Name": "main", "Environment": "prod", "Owner": "platform-team"}))
    graph.add_resource(_resource("subnet", CanonicalResourceType.NETWORK_SUBNET,
        depends_on=frozenset({"vpc"}), tags={"Environment": "prod"}))
    graph.add_resource(_resource("sg", CanonicalResourceType.NETWORK_FIREWALL_RULE,
        depends_on=frozenset({"vpc"})))
    graph.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE,
        depends_on=frozenset({"subnet", "sg"}),
        tags={"Name": "app", "Environment": "prod", "Criticality": "high", "Application": "payments-api"}))
    graph.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE,
        depends_on=frozenset({"subnet"}),
        tags={"Environment": "prod", "Tier": "tier1"}))
    graph.add_resource(_resource("bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET))
    return graph


# --- AI Engine Tests ---

class TestAIEngine:
    def test_fallback_when_no_api_key(self):
        engine = AIEngine(api_key=None)
        assert not engine.is_available

    def test_infrastructure_explanation_fallback(self):
        engine = AIEngine(api_key=None)
        graph = _sample_graph()
        result = engine.explain_infrastructure(graph)
        assert result.analysis_type is AIAnalysisType.INFRASTRUCTURE_EXPLANATION
        assert result.fallback is True
        assert len(result.content) > 0
        assert len(result.key_findings) > 0

    def test_risk_analysis_fallback(self):
        engine = AIEngine(api_key=None)
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        result = engine.analyze_migration_risks(graph, translation, assessment)
        assert result.fallback is True
        assert result.analysis_type is AIAnalysisType.MIGRATION_RISK_ANALYSIS

    def test_optimization_suggestions_fallback(self):
        engine = AIEngine(api_key=None)
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        result = engine.suggest_optimizations(graph, translation, 500.0, 420.0)
        assert result.fallback is True
        assert len(result.recommendations) > 0

    def test_architecture_summary_fallback(self):
        engine = AIEngine(api_key=None)
        graph = _sample_graph()
        result = engine.generate_architecture_summary(graph)
        assert result.fallback is True
        assert "tiers" in result.content.lower() or "architecture" in result.content.lower()

    def test_documentation_fallback(self):
        engine = AIEngine(api_key=None)
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        assessment = AssessmentEngine().assess(graph, translation)
        result = engine.generate_documentation(graph, translation, assessment)
        assert result.fallback is True
        assert "Runbook" in result.content
        assert "Rollback" in result.content

    def test_prompt_templates_cover_all_analysis_types(self):
        from migration_factory.ai.engine import PROMPT_TEMPLATES
        for at in AIAnalysisType:
            if at in {AIAnalysisType.ROOT_CAUSE_ANALYSIS, AIAnalysisType.MIGRATION_PLAN_NARRATIVE}:
                continue  # Future
            assert at in PROMPT_TEMPLATES, f"Missing prompt template for {at}"


# --- Knowledge Graph Tests ---

class TestKnowledgeGraph:
    def test_builds_typed_edges(self):
        graph = _sample_graph()
        report = KnowledgeGraphEngine().analyze(graph)
        assert report.total_edges > 0
        edge_types = {e.dependency_type for e in report.typed_edges}
        assert DependencyType.NETWORK in edge_types

    def test_classifies_network_dependencies(self):
        graph = _sample_graph()
        report = KnowledgeGraphEngine().analyze(graph)
        # instance -> subnet should be NETWORK type
        subnet_edge = next(
            (e for e in report.typed_edges if e.source_id == "instance" and e.target_id == "subnet"),
            None,
        )
        assert subnet_edge is not None
        assert subnet_edge.dependency_type is DependencyType.NETWORK

    def test_impact_analysis_blast_radius(self):
        graph = _sample_graph()
        report = KnowledgeGraphEngine().analyze(graph)
        # VPC should have the highest blast radius (everything depends on it)
        vpc_impact = next(ir for ir in report.impact_analysis if ir.resource_id == "vpc")
        assert vpc_impact.blast_radius > 0

    def test_critical_resources_identified(self):
        graph = _sample_graph()
        report = KnowledgeGraphEngine().analyze(graph)
        # VPC should be critical (many dependents)
        assert "vpc" in report.critical_resources

    def test_application_groups(self):
        graph = _sample_graph()
        report = KnowledgeGraphEngine().analyze(graph)
        assert len(report.application_groups) > 0

    def test_dependency_type_counts(self):
        graph = _sample_graph()
        report = KnowledgeGraphEngine().analyze(graph)
        assert sum(report.dependency_type_counts.values()) == report.total_edges


# --- Rollback Planner Tests ---

class TestRollbackPlanner:
    def test_generates_rollback_plan(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        plan = RollbackPlanner().plan(graph, translation)
        assert plan.total_steps == 6
        assert plan.estimated_duration_minutes > 0
        assert len(plan.pre_rollback_checks) > 0
        assert len(plan.post_rollback_verification) > 0
        assert len(plan.state_restoration) > 0

    def test_destroy_order_is_reverse_of_deploy(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        plan = RollbackPlanner().plan(graph, translation)
        topo = graph.topological_order()
        assert plan.terraform_destroy_order == list(reversed(topo))

    def test_stateful_resources_flagged_high_risk(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        plan = RollbackPlanner().plan(graph, translation)
        db_step = next(s for s in plan.rollback_steps if s.resource_id == "db")
        assert "persistent data" in db_step.risk

    def test_risk_assessment_reflects_stateful_count(self):
        graph = _sample_graph()
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        translation = TranslationEngine(matrix=matrix).translate(graph)
        plan = RollbackPlanner().plan(graph, translation)
        # graph has DB + bucket = stateful resources
        assert "MEDIUM" in plan.risk_assessment or "HIGH" in plan.risk_assessment


# --- Discovery Engine Tests ---

class TestDiscoveryEngine:
    def test_enriches_from_environment_tag(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC,
            tags={"Environment": "production"}))
        report = DiscoveryEngine().enrich(graph)
        assert report.resources_enriched == 1
        assert graph.resources["vpc"].environment == "production"

    def test_enriches_from_owner_tag(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC,
            tags={"Team": "platform-engineering"}))
        DiscoveryEngine().enrich(graph)
        assert graph.resources["vpc"].owner == "platform-engineering"

    def test_criticality_normalized(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE,
            tags={"Tier": "tier1"}))
        DiscoveryEngine().enrich(graph)
        assert graph.resources["db"].criticality == "critical"

    def test_criticality_inferred_from_environment(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE,
            tags={"Environment": "production"}))
        DiscoveryEngine().enrich(graph)
        assert graph.resources["db"].criticality == "critical"

    def test_application_extracted(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("instance", CanonicalResourceType.COMPUTE_INSTANCE,
            tags={"Application": "payments-api"}))
        DiscoveryEngine().enrich(graph)
        assert graph.resources["instance"].application == "payments-api"

    def test_unclassified_resources_reported(self):
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("bare", CanonicalResourceType.COMPUTE_INSTANCE, tags={}))
        report = DiscoveryEngine().enrich(graph)
        assert "bare" in report.unclassified_resources

    def test_full_enrichment_on_sample_graph(self):
        graph = _sample_graph()
        report = DiscoveryEngine().enrich(graph)
        # VPC has Environment + Owner tags -> should be enriched
        assert report.resources_enriched > 0
        assert graph.resources["vpc"].environment == "prod"
        assert graph.resources["vpc"].owner == "platform-team"
        assert graph.resources["instance"].application == "payments-api"
