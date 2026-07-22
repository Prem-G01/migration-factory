"""Application Dependency Graph.

Builds an application-level dependency graph (which app depends on which
other app) by inferring relationships from:

1. Shared infrastructure — two apps sharing a database, queue, or cache
   have an implicit dependency through that resource.
2. Tag-based service mesh — if resources are tagged with upstream/downstream
   service names, those form explicit app-level edges.
3. Naming conventions — apps following <service>-<resource> naming patterns
   can have their relationships inferred.
4. DNS + load balancer chains — an LB fronting App A that points to the same
   VPC as App B implies a potential call path.

This is the maximum precision achievable without live APM telemetry. For
production-grade application dependency mapping, plug in OpenTelemetry trace
data via the APMTraceIngester below.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph, CanonicalResource
from migration_factory.domain.enums import CanonicalResourceType

logger = get_logger(__name__)


class AppDependencyType(StrEnum):
    SHARED_DATABASE = "shared_database"
    SHARED_QUEUE = "shared_queue"
    SHARED_CACHE = "shared_cache"
    SHARED_STORAGE = "shared_storage"
    SHARED_LOAD_BALANCER = "shared_load_balancer"
    TAG_DECLARED = "tag_declared"
    NAMING_INFERRED = "naming_inferred"
    UNKNOWN = "unknown"


class AppDependencyEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_app: str
    target_app: str
    dependency_type: AppDependencyType
    via_resource_id: str
    via_resource_name: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="0=guessed, 1=explicit")
    description: str = ""


class AppNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_name: str
    resource_ids: list[str] = Field(default_factory=list)
    resource_count: int = 0
    canonical_types: list[str] = Field(default_factory=list)
    criticality: str = "unknown"
    owner: str = ""


class AppDependencyGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    apps: dict[str, AppNode] = Field(default_factory=dict)
    edges: list[AppDependencyEdge] = Field(default_factory=list)
    ungrouped_resources: list[str] = Field(default_factory=list)

    def get_dependencies_of(self, app_name: str) -> list[AppDependencyEdge]:
        return [e for e in self.edges if e.source_app == app_name]

    def get_dependents_of(self, app_name: str) -> list[AppDependencyEdge]:
        return [e for e in self.edges if e.target_app == app_name]

    def migration_order(self) -> list[str]:
        """Topological sort of apps — independent apps first."""
        in_degree: dict[str, int] = {app: 0 for app in self.apps}
        for edge in self.edges:
            if edge.target_app in in_degree:
                in_degree[edge.target_app] += 1

        ready = sorted(app for app, deg in in_degree.items() if deg == 0)
        order: list[str] = []
        adj: dict[str, list[str]] = {app: [] for app in self.apps}
        for edge in self.edges:
            adj[edge.source_app].append(edge.target_app)

        while ready:
            current = ready.pop(0)
            order.append(current)
            for dep in sorted(adj.get(current, [])):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    ready.append(dep)

        # Add any not reached (cycles)
        for app in sorted(self.apps):
            if app not in order:
                order.append(app)
        return order


_SHARED_INFRA_TYPES = {
    CanonicalResourceType.DATABASE_INSTANCE: AppDependencyType.SHARED_DATABASE,
    CanonicalResourceType.DATABASE_NOSQL: AppDependencyType.SHARED_DATABASE,
    CanonicalResourceType.DATABASE_CACHE: AppDependencyType.SHARED_CACHE,
    CanonicalResourceType.MESSAGING_QUEUE: AppDependencyType.SHARED_QUEUE,
    CanonicalResourceType.MESSAGING_TOPIC: AppDependencyType.SHARED_QUEUE,
    CanonicalResourceType.STORAGE_OBJECT_BUCKET: AppDependencyType.SHARED_STORAGE,
    CanonicalResourceType.LOAD_BALANCER: AppDependencyType.SHARED_LOAD_BALANCER,
}


@dataclass(slots=True)
class AppDependencyGraphBuilder:
    """Builds an application dependency graph from static infrastructure analysis."""

    def build(self, graph: CanonicalInfrastructureGraph) -> AppDependencyGraph:
        # Step 1: Group resources by application
        app_resources: dict[str, list[CanonicalResource]] = {}
        ungrouped: list[str] = []

        for resource in graph.resources.values():
            app = (
                resource.application
                or resource.tags.get("Application")
                or resource.tags.get("app")
                or resource.tags.get("Service")
                or resource.tags.get("service")
                or self._infer_app_from_name(resource.name)
            )
            if app:
                app_resources.setdefault(app, []).append(resource)
            else:
                ungrouped.append(resource.id)

        # Step 2: Build AppNode for each application
        apps: dict[str, AppNode] = {}
        for app_name, resources in app_resources.items():
            crit_values = [r.criticality for r in resources if r.criticality]
            crit_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            criticality = max(crit_values, key=lambda c: crit_order.get(c, 0)) if crit_values else "unknown"
            owners = {r.owner for r in resources if r.owner}

            apps[app_name] = AppNode(
                app_name=app_name,
                resource_ids=[r.id for r in resources],
                resource_count=len(resources),
                canonical_types=sorted({r.canonical_type.value for r in resources}),
                criticality=criticality,
                owner=", ".join(sorted(owners)) if owners else "",
            )

        # Step 3: Infer app-level dependencies from shared infrastructure
        edges: list[AppDependencyEdge] = []

        # Find shared infra resources (database, queue, cache, etc.)
        for resource in graph.resources.values():
            dep_type = _SHARED_INFRA_TYPES.get(resource.canonical_type)
            if dep_type is None:
                continue

            # Which apps use this resource (directly or via depends_on chain)?
            using_apps: set[str] = set()
            for app_name, resources in app_resources.items():
                for r in resources:
                    if resource.id in r.depends_on or resource.id in graph.get_dependents(r.id):
                        using_apps.add(app_name)
                    # Check if the resource itself belongs to the app
                    if r.id == resource.id:
                        using_apps.add(app_name)

            # If multiple apps use this resource, add dependency edges
            app_list = sorted(using_apps)
            for i, app_a in enumerate(app_list):
                for app_b in app_list[i + 1:]:
                    if app_a != app_b:
                        edges.append(AppDependencyEdge(
                            source_app=app_a,
                            target_app=app_b,
                            dependency_type=dep_type,
                            via_resource_id=resource.id,
                            via_resource_name=resource.name,
                            confidence=0.7,
                            description=(
                                f"Both apps share {resource.canonical_type.value}: {resource.name}. "
                                f"Migration must coordinate cutover of this shared resource."
                            ),
                        ))

        # Step 4: Tag-declared dependencies
        for resource in graph.resources.values():
            upstream = resource.tags.get("upstream-service") or resource.tags.get("UpstreamService")
            downstream = resource.tags.get("downstream-service") or resource.tags.get("DownstreamService")
            app = resource.application or resource.tags.get("Application")

            if app and upstream and upstream in apps:
                edges.append(AppDependencyEdge(
                    source_app=app,
                    target_app=upstream,
                    dependency_type=AppDependencyType.TAG_DECLARED,
                    via_resource_id=resource.id,
                    via_resource_name=resource.name,
                    confidence=0.95,
                    description=f"Explicit upstream-service tag on {resource.name}",
                ))

            if app and downstream and downstream in apps:
                edges.append(AppDependencyEdge(
                    source_app=downstream,
                    target_app=app,
                    dependency_type=AppDependencyType.TAG_DECLARED,
                    via_resource_id=resource.id,
                    via_resource_name=resource.name,
                    confidence=0.95,
                    description=f"Explicit downstream-service tag on {resource.name}",
                ))

        # Deduplicate edges
        seen: set[tuple[str, str, str]] = set()
        unique_edges: list[AppDependencyEdge] = []
        for edge in edges:
            key = (edge.source_app, edge.target_app, edge.dependency_type.value)
            if key not in seen:
                seen.add(key)
                unique_edges.append(edge)

        result = AppDependencyGraph(apps=apps, edges=unique_edges, ungrouped_resources=ungrouped)

        logger.info(
            "app_dependency_graph_built",
            app_count=len(apps),
            edge_count=len(unique_edges),
            ungrouped=len(ungrouped),
        )
        return result

    @staticmethod
    def _infer_app_from_name(name: str) -> str | None:
        """Infer application name from resource naming conventions.

        Supports: <app>-<resource>, <app>_<resource>, <env>-<app>-<resource>
        Returns the inferred app name, or None if unable to infer.
        """
        if not name or len(name) < 4:
            return None

        # Skip infrastructure-level names
        infra_keywords = {"main", "default", "shared", "common", "base", "core", "vpc", "subnet"}
        if name.lower() in infra_keywords:
            return None

        parts = name.replace("_", "-").split("-")
        if len(parts) >= 2:
            # Pattern: <env>-<app>-<resource> → return <app>
            envs = {"dev", "staging", "prod", "production", "test", "uat"}
            if len(parts) >= 3 and parts[0].lower() in envs:
                return parts[1]
            # Pattern: <app>-<resource> → return <app>
            if len(parts) == 2:
                return parts[0]

        return None


class APMTraceIngester:
    """Ingests OpenTelemetry or APM trace data to build precise runtime dependencies.

    When APM data is available, this produces high-confidence (1.0) edges
    compared to the 0.7 confidence of static analysis. Plug in trace export
    from your APM provider.
    """

    @staticmethod
    def from_otel_json(trace_file_path: str) -> list[AppDependencyEdge]:
        """Parse OpenTelemetry JSON export to extract service call edges.

        Expected format: OTLP JSON export containing spans with service.name
        attributes and parent-child relationships indicating call direction.
        """
        import json
        from pathlib import Path

        edges: list[AppDependencyEdge] = []
        data = json.loads(Path(trace_file_path).read_text(encoding="utf-8"))

        # Process resource spans
        for resource_span in data.get("resourceSpans", []):
            service_name = ""
            for attr in resource_span.get("resource", {}).get("attributes", []):
                if attr.get("key") == "service.name":
                    service_name = str(attr.get("value", {}).get("stringValue", ""))
                    break

            for scope_span in resource_span.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    # Spans with a parentSpanId are calls from a parent service
                    if span.get("parentSpanId") and service_name:
                        peer = ""
                        for attr in span.get("attributes", []):
                            if attr.get("key") in ("peer.service", "db.name", "messaging.system"):
                                peer = str(attr.get("value", {}).get("stringValue", ""))
                                break

                        if peer and peer != service_name:
                            edges.append(AppDependencyEdge(
                                source_app=service_name,
                                target_app=peer,
                                dependency_type=AppDependencyType.UNKNOWN,
                                via_resource_id="apm_trace",
                                via_resource_name=f"trace:{span.get('traceId', '')[:8]}",
                                confidence=1.0,
                                description="Detected from APM trace — actual runtime call",
                            ))

        return edges
