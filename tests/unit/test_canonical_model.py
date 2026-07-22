from __future__ import annotations

import pytest

from migration_factory.core.exceptions import DependencyGraphError
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
    SourceLocation,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider


def _resource(rid: str, depends_on: frozenset[str] = frozenset()) -> CanonicalResource:
    return CanonicalResource(
        id=rid,
        canonical_type=CanonicalResourceType.COMPUTE_INSTANCE,
        source_provider=CloudProvider.AWS,
        source_type="aws_instance",
        name=rid,
        depends_on=depends_on,
        source_location=SourceLocation(source_system="test", source_path="test"),
    )


def test_add_resource_rejects_duplicate_ids() -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("a"))
    with pytest.raises(DependencyGraphError):
        graph.add_resource(_resource("a"))


def test_blank_id_rejected() -> None:
    with pytest.raises(ValueError):
        _resource("   ")


def test_topological_order_respects_dependencies() -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("vpc"))
    graph.add_resource(_resource("subnet", depends_on=frozenset({"vpc"})))
    graph.add_resource(_resource("instance", depends_on=frozenset({"subnet"})))

    order = graph.topological_order()

    assert order.index("vpc") < order.index("subnet") < order.index("instance")
    assert set(order) == {"vpc", "subnet", "instance"}


def test_topological_order_is_deterministic_for_independent_resources() -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("b"))
    graph.add_resource(_resource("a"))
    graph.add_resource(_resource("c"))

    # No dependencies between a/b/c -> deterministic alphabetical tie-break.
    assert graph.topological_order() == ["a", "b", "c"]


def test_circular_dependency_raises_with_cycle_members_named() -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("a", depends_on=frozenset({"b"})))
    graph.add_resource(_resource("b", depends_on=frozenset({"a"})))

    with pytest.raises(DependencyGraphError) as exc_info:
        graph.topological_order()

    assert set(exc_info.value.context["resources_in_cycle"]) == {"a", "b"}


def test_destroy_order_is_reverse_of_deployment_order() -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("vpc"))
    graph.add_resource(_resource("subnet", depends_on=frozenset({"vpc"})))

    assert graph.destroy_order() == list(reversed(graph.topological_order()))


def test_dangling_dependency_detected_non_fatally() -> None:
    graph = CanonicalInfrastructureGraph()
    graph.add_resource(_resource("subnet", depends_on=frozenset({"missing-vpc"})))

    dangling = graph.validate_references()

    assert dangling == ["missing-vpc"]
