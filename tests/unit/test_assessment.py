from __future__ import annotations

import pytest

from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.assessment.models import (
    DowntimeClass,
    MigrationStrategy,
    RiskLevel,
)
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
    SourceLocation,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
from migration_factory.translation.models import SupportStatus


def _loc() -> SourceLocation:
    return SourceLocation(source_system="test", source_path="test")


def _resource(
    rid: str,
    ctype: CanonicalResourceType,
    depends_on: frozenset[str] = frozenset(),
) -> CanonicalResource:
    return CanonicalResource(
        id=rid,
        canonical_type=ctype,
        source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}",
        name=rid,
        depends_on=depends_on,
        source_location=_loc(),
    )


@pytest.fixture()
def engine() -> AssessmentEngine:
    return AssessmentEngine()


@pytest.fixture()
def aws_gcp_matrix():
    return load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)


def test_supported_resource_gets_rehost_strategy(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))

    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    ra = assessment.resource_assessments[0]
    assert ra.strategy is MigrationStrategy.REHOST
    assert ra.support_status is SupportStatus.SUPPORTED
    assert ra.blockers == []


def test_manual_resource_gets_manual_strategy_with_blockers(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE))

    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    ra = assessment.resource_assessments[0]
    assert ra.strategy is MigrationStrategy.MANUAL
    assert len(ra.blockers) > 0


def test_database_gets_high_downtime(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE))

    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    ra = assessment.resource_assessments[0]
    assert ra.downtime is DowntimeClass.HIGH


def test_dependency_count_feeds_score(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
    graph.add_resource(
        _resource("subnet", CanonicalResourceType.NETWORK_SUBNET, frozenset({"vpc"}))
    )
    graph.add_resource(
        _resource(
            "instance",
            CanonicalResourceType.COMPUTE_INSTANCE,
            frozenset({"subnet", "vpc"}),
        )
    )

    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    # Instance has 2 deps -> dependency_load = 8 (2 * 4)
    instance_ra = next(
        a for a in assessment.resource_assessments if a.resource_id == "instance"
    )
    assert instance_ra.dependency_count == 2
    assert instance_ra.score_breakdown.dependency_load == 8


def test_score_is_clamped_1_to_100(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    # Use a resource type that will have high complexity
    graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE))

    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    for ra in assessment.resource_assessments:
        assert 1 <= ra.complexity_score <= 100


def test_phases_respect_category_order(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    # Add resources across multiple categories
    graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
    graph.add_resource(
        _resource("subnet", CanonicalResourceType.NETWORK_SUBNET, frozenset({"vpc"}))
    )
    graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE))
    graph.add_resource(_resource("bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET))
    graph.add_resource(
        _resource(
            "instance",
            CanonicalResourceType.COMPUTE_INSTANCE,
            frozenset({"subnet"}),
        )
    )

    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    phase_names = [p.name for p in assessment.phases]
    assert phase_names == [
        "Networking",
        "IAM & Security",
        "Storage",
        "Compute & Load Balancing",
    ]
    # Networking phase should include VPC before subnet (topo order respected)
    net_phase = assessment.phases[0]
    assert net_phase.resource_ids.index("vpc") < net_phase.resource_ids.index("subnet")


def test_high_risk_when_multiple_manual_resources(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("role1", CanonicalResourceType.IAM_ROLE))
    graph.add_resource(
        CanonicalResource(
            id="role2",
            canonical_type=CanonicalResourceType.IAM_ROLE,
            source_provider=CloudProvider.AWS,
            source_type="aws_iam_role",
            name="role2",
            source_location=_loc(),
        )
    )

    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    assert assessment.risk_level is RiskLevel.HIGH


def test_low_risk_when_all_supported(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
    graph.add_resource(_resource("bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET))

    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    assert assessment.risk_level is RiskLevel.LOW


def test_recommendation_mentions_blockers(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE))

    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    assert "blocking issue" in assessment.recommendation.lower()


def test_empty_graph_produces_minimal_assessment(engine, aws_gcp_matrix) -> None:
    graph = CanonicalInfrastructureGraph()
    translation = TranslationEngine(matrix=aws_gcp_matrix).translate(graph)
    assessment = engine.assess(graph, translation)

    assert assessment.overall_complexity_score == 1
    assert assessment.resource_assessments == []
    assert assessment.phases == []
