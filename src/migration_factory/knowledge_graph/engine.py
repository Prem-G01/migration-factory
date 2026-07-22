"""Infrastructure Knowledge Graph.

Extends the basic `depends_on` edges in the Canonical Model with typed,
classified dependency relationships and graph analysis operations: impact
analysis (blast radius), dependency classification, critical path detection,
and resource grouping by application/service.

This is NOT a replacement for the canonical graph — it's a read-only
analytical view built ON TOP of it for the AI Engine, Assessment Engine,
and Migration Planner to consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.domain.enums import CanonicalResourceType

logger = get_logger(__name__)


class DependencyType(StrEnum):
    """Classification of why one resource depends on another."""

    NETWORK = "network"  # VPC, subnet, peering
    IAM = "iam"  # role, policy, service account
    STORAGE = "storage"  # bucket, volume, file system
    DATABASE = "database"  # DB instance, cache
    RUNTIME = "runtime"  # compute needs subnet/SG
    DNS = "dns"  # record points to resource
    SECURITY = "security"  # certificate, secrets
    MESSAGING = "messaging"  # topic/queue dependency
    UNKNOWN = "unknown"


class DependencyEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(..., description="Resource that depends on target")
    target_id: str = Field(..., description="Resource being depended upon")
    dependency_type: DependencyType
    is_critical: bool = Field(default=False, description="If True, source cannot function without target")


class ImpactAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    resource_name: str
    blast_radius: int = Field(..., description="Number of resources impacted if this resource fails")
    directly_impacted: list[str] = Field(default_factory=list)
    transitively_impacted: list[str] = Field(default_factory=list)
    critical_path: bool = Field(default=False, description="On the longest dependency chain")


class KnowledgeGraphReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_edges: int
    typed_edges: list[DependencyEdge] = Field(default_factory=list)
    impact_analysis: list[ImpactAnalysisResult] = Field(default_factory=list)
    critical_resources: list[str] = Field(default_factory=list)
    application_groups: dict[str, list[str]] = Field(default_factory=dict)
    dependency_type_counts: dict[str, int] = Field(default_factory=dict)


# Heuristic: classify dependency type based on the canonical types involved
_DEP_TYPE_RULES: dict[tuple[str, str], DependencyType] = {}


def _infer_dependency_type(
    source_type: CanonicalResourceType, target_type: CanonicalResourceType
) -> DependencyType:
    """Classify a dependency edge based on the canonical types of source and target."""
    target_category = target_type.value.split(".")[0]
    source_category = source_type.value.split(".")[0]

    if target_category == "network":
        return DependencyType.NETWORK
    if target_category == "iam":
        return DependencyType.IAM
    if target_category == "storage":
        return DependencyType.STORAGE
    if target_category == "database":
        return DependencyType.DATABASE
    if target_category == "dns":
        return DependencyType.DNS
    if target_category == "security" or target_category == "secrets":
        return DependencyType.SECURITY
    if target_category == "messaging":
        return DependencyType.MESSAGING
    if source_category == "compute":
        return DependencyType.RUNTIME
    return DependencyType.UNKNOWN


@dataclass(slots=True)
class KnowledgeGraphEngine:
    """Builds a typed knowledge graph from the canonical infrastructure graph."""

    def analyze(self, graph: CanonicalInfrastructureGraph) -> KnowledgeGraphReport:
        # Build typed edges
        typed_edges: list[DependencyEdge] = []
        for resource in graph.resources.values():
            for dep_id in resource.depends_on:
                if dep_id not in graph.resources:
                    continue
                target = graph.resources[dep_id]
                dep_type = _infer_dependency_type(resource.canonical_type, target.canonical_type)
                is_critical = dep_type in {DependencyType.NETWORK, DependencyType.IAM, DependencyType.DATABASE}

                typed_edges.append(DependencyEdge(
                    source_id=resource.id,
                    target_id=dep_id,
                    dependency_type=dep_type,
                    is_critical=is_critical,
                ))

        # Impact analysis: for each resource, compute blast radius
        impact_results: list[ImpactAnalysisResult] = []
        for resource in graph.resources.values():
            directly_impacted = graph.get_dependents(resource.id)
            transitively_impacted = self._transitive_dependents(graph, resource.id)
            blast_radius = len(transitively_impacted)

            impact_results.append(ImpactAnalysisResult(
                resource_id=resource.id,
                resource_name=resource.name,
                blast_radius=blast_radius,
                directly_impacted=directly_impacted,
                transitively_impacted=transitively_impacted,
                critical_path=blast_radius > len(graph.resources) * 0.3,
            ))

        # Sort by blast radius descending
        impact_results.sort(key=lambda x: x.blast_radius, reverse=True)

        # Critical resources: those with highest blast radius
        critical = [ir.resource_id for ir in impact_results if ir.blast_radius > 0][:5]

        # Application groups: group by 'application' tag or canonical type category
        app_groups: dict[str, list[str]] = {}
        for resource in graph.resources.values():
            app = resource.application or resource.tags.get("Application") or resource.tags.get("app") or "ungrouped"
            app_groups.setdefault(app, []).append(resource.id)

        # Dependency type counts
        type_counts: dict[str, int] = {}
        for edge in typed_edges:
            type_counts[edge.dependency_type.value] = type_counts.get(edge.dependency_type.value, 0) + 1

        report = KnowledgeGraphReport(
            total_edges=len(typed_edges),
            typed_edges=typed_edges,
            impact_analysis=impact_results,
            critical_resources=critical,
            application_groups=app_groups,
            dependency_type_counts=type_counts,
        )

        logger.info(
            "knowledge_graph_analyzed",
            total_edges=len(typed_edges),
            critical_resources=len(critical),
            app_groups=len(app_groups),
        )
        return report

    @staticmethod
    def _transitive_dependents(graph: CanonicalInfrastructureGraph, resource_id: str) -> list[str]:
        """BFS to find all resources transitively impacted by this resource."""
        visited: set[str] = set()
        queue = [resource_id]

        while queue:
            current = queue.pop(0)
            dependents = graph.get_dependents(current)
            for dep in dependents:
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)

        return sorted(visited)
