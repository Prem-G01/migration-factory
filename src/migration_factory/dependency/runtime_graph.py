"""Runtime Dependency Graph.

Infers runtime service-to-service call patterns from static infrastructure
analysis. This is the maximum fidelity achievable without live APM data.

Inference sources:
1. Security group rules — port 5432 → PostgreSQL dependency, port 6379 → Redis, etc.
2. Environment variables in Lambda/ECS — DB_HOST, REDIS_URL patterns
3. Resource co-location — compute in the same subnet as a database likely connects to it
4. IAM permissions — a role with s3:GetObject implies runtime S3 reads
5. VPC endpoints — a VPC endpoint for DynamoDB implies compute in that VPC uses it

For production precision, ingest OpenTelemetry traces via APMTraceIngester
in app_graph.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.domain.enums import CanonicalResourceType

logger = get_logger(__name__)


class RuntimeCallType(StrEnum):
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    STORAGE = "storage"
    API = "api"
    DNS = "dns"
    IAM = "iam"
    INFERRED = "inferred"


class RuntimeEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    caller_id: str
    callee_id: str
    call_type: RuntimeCallType
    protocol: str = ""
    port: int | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: str = ""


class RuntimeDependencyGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edges: list[RuntimeEdge] = Field(default_factory=list)
    unresolved_endpoints: list[str] = Field(default_factory=list)

    def callers_of(self, resource_id: str) -> list[RuntimeEdge]:
        return [e for e in self.edges if e.callee_id == resource_id]

    def callees_of(self, resource_id: str) -> list[RuntimeEdge]:
        return [e for e in self.edges if e.caller_id == resource_id]

    @property
    def high_confidence_edges(self) -> list[RuntimeEdge]:
        return [e for e in self.edges if e.confidence >= 0.8]


# Port → runtime dependency type mapping
_PORT_CALL_TYPE: dict[int, tuple[RuntimeCallType, str]] = {
    5432: (RuntimeCallType.DATABASE, "PostgreSQL"),
    3306: (RuntimeCallType.DATABASE, "MySQL"),
    1433: (RuntimeCallType.DATABASE, "MSSQL"),
    27017: (RuntimeCallType.DATABASE, "MongoDB"),
    6379: (RuntimeCallType.CACHE, "Redis"),
    11211: (RuntimeCallType.CACHE, "Memcached"),
    5672: (RuntimeCallType.QUEUE, "AMQP/RabbitMQ"),
    9092: (RuntimeCallType.QUEUE, "Kafka"),
    443: (RuntimeCallType.API, "HTTPS"),
    80: (RuntimeCallType.API, "HTTP"),
    8080: (RuntimeCallType.API, "HTTP-alt"),
    53: (RuntimeCallType.DNS, "DNS"),
}

# Environment variable patterns that imply runtime dependencies
_ENV_PATTERNS: list[tuple[str, RuntimeCallType]] = [
    ("DB_HOST", RuntimeCallType.DATABASE),
    ("DATABASE_URL", RuntimeCallType.DATABASE),
    ("POSTGRES_HOST", RuntimeCallType.DATABASE),
    ("MYSQL_HOST", RuntimeCallType.DATABASE),
    ("REDIS_URL", RuntimeCallType.CACHE),
    ("REDIS_HOST", RuntimeCallType.CACHE),
    ("CACHE_URL", RuntimeCallType.CACHE),
    ("QUEUE_URL", RuntimeCallType.QUEUE),
    ("SQS_URL", RuntimeCallType.QUEUE),
    ("AMQP_URL", RuntimeCallType.QUEUE),
    ("S3_BUCKET", RuntimeCallType.STORAGE),
    ("GCS_BUCKET", RuntimeCallType.STORAGE),
    ("STORAGE_BUCKET", RuntimeCallType.STORAGE),
    ("API_URL", RuntimeCallType.API),
    ("SERVICE_URL", RuntimeCallType.API),
    ("ENDPOINT", RuntimeCallType.API),
]


@dataclass(slots=True)
class RuntimeDependencyGraphBuilder:
    """Infers runtime dependencies from static infrastructure analysis."""

    def build(self, graph: CanonicalInfrastructureGraph) -> RuntimeDependencyGraph:
        edges: list[RuntimeEdge] = []
        unresolved: list[str] = []

        # 1. Infer from security group rules (port patterns)
        edges.extend(self._infer_from_security_groups(graph))

        # 2. Infer from compute → shared infra co-location (subnet-level)
        edges.extend(self._infer_from_colocation(graph))

        # 3. Infer from environment variables in Lambda/ECS attributes
        edges.extend(self._infer_from_env_vars(graph))

        # 4. Infer from IAM role permissions
        edges.extend(self._infer_from_iam(graph))

        # Deduplicate
        seen: set[tuple[str, str, str]] = set()
        unique: list[RuntimeEdge] = []
        for edge in edges:
            key = (edge.caller_id, edge.callee_id, edge.call_type.value)
            if key not in seen:
                seen.add(key)
                unique.append(edge)

        result = RuntimeDependencyGraph(edges=unique, unresolved_endpoints=unresolved)

        logger.info(
            "runtime_dependency_graph_built",
            edge_count=len(unique),
            high_confidence=len(result.high_confidence_edges),
        )
        return result

    @staticmethod
    def _infer_from_security_groups(graph: CanonicalInfrastructureGraph) -> list[RuntimeEdge]:
        """Infer runtime calls from security group ingress rules."""
        edges: list[RuntimeEdge] = []
        sg_resources = [r for r in graph.resources.values() if r.canonical_type is CanonicalResourceType.NETWORK_FIREWALL_RULE]

        for sg in sg_resources:
            ingress = sg.native_attributes.get("ingress", [])
            if not isinstance(ingress, list):
                continue

            for rule in ingress:
                if not isinstance(rule, dict):
                    continue
                from_port = rule.get("from_port", 0)
                to_port = rule.get("to_port", 0)

                for port, (call_type, protocol) in _PORT_CALL_TYPE.items():
                    if from_port <= port <= to_port:
                        # SG allows inbound → resource behind this SG is a callee
                        # The dependents of this SG are the callers
                        for dependent_id in graph.get_dependents(sg.id):
                            edges.append(RuntimeEdge(
                                caller_id="external",
                                callee_id=dependent_id,
                                call_type=call_type,
                                protocol=protocol,
                                port=port,
                                confidence=0.65,
                                evidence=f"SG {sg.name} allows inbound {protocol} (port {port})",
                            ))

        return edges

    @staticmethod
    def _infer_from_colocation(graph: CanonicalInfrastructureGraph) -> list[RuntimeEdge]:
        """Compute in same subnet as database/cache → likely calls it."""
        edges: list[RuntimeEdge] = []

        # Group resources by subnet
        subnet_resources: dict[str, list[str]] = {}
        for resource in graph.resources.values():
            subnet_id = resource.native_attributes.get("subnet_id")
            if subnet_id and isinstance(subnet_id, str):
                subnet_resources.setdefault(subnet_id, []).append(resource.id)

        # Within each subnet, compute → database/cache edges
        compute_types = {CanonicalResourceType.COMPUTE_INSTANCE, CanonicalResourceType.COMPUTE_CONTAINER_SERVICE}
        data_types = {
            CanonicalResourceType.DATABASE_INSTANCE: RuntimeCallType.DATABASE,
            CanonicalResourceType.DATABASE_NOSQL: RuntimeCallType.DATABASE,
            CanonicalResourceType.DATABASE_CACHE: RuntimeCallType.CACHE,
        }

        for _, resource_ids in subnet_resources.items():
            computes = [r for rid in resource_ids if (r := graph.resources.get(rid)) and r.canonical_type in compute_types]
            data_resources = [r for rid in resource_ids if (r := graph.resources.get(rid)) and r.canonical_type in data_types]

            for compute in computes:
                for data_res in data_resources:
                    call_type = data_types[data_res.canonical_type]
                    edges.append(RuntimeEdge(
                        caller_id=compute.id,
                        callee_id=data_res.id,
                        call_type=call_type,
                        confidence=0.55,
                        evidence=f"Co-located in same subnet ({compute.name} → {data_res.name})",
                    ))

        return edges

    @staticmethod
    def _infer_from_env_vars(graph: CanonicalInfrastructureGraph) -> list[RuntimeEdge]:
        """Infer from environment variable names in Lambda/ECS attributes."""
        edges: list[RuntimeEdge] = []
        serverless = [r for r in graph.resources.values() if r.canonical_type in {
            CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION,
            CanonicalResourceType.COMPUTE_CONTAINER_SERVICE,
        }]

        for resource in serverless:
            env_vars = resource.native_attributes.get("environment", {})
            variables = env_vars.get("variables", env_vars) if isinstance(env_vars, dict) else {}

            if not isinstance(variables, dict):
                continue

            for env_key, env_val in variables.items():
                for pattern, call_type in _ENV_PATTERNS:
                    if pattern in str(env_key).upper():
                        # Try to resolve the target resource
                        target = None
                        for r in graph.resources.values():
                            if r.name and r.name in str(env_val):
                                target = r
                                break

                        if target:
                            edges.append(RuntimeEdge(
                                caller_id=resource.id,
                                callee_id=target.id,
                                call_type=call_type,
                                confidence=0.85,
                                evidence=f"Env var {env_key}={env_val} references {target.name}",
                            ))
                        else:
                            edges.append(RuntimeEdge(
                                caller_id=resource.id,
                                callee_id=f"unresolved:{env_val}",
                                call_type=call_type,
                                confidence=0.7,
                                evidence=f"Env var {env_key} pattern suggests {call_type.value} dependency",
                            ))

        return edges

    @staticmethod
    def _infer_from_iam(graph: CanonicalInfrastructureGraph) -> list[RuntimeEdge]:
        """Infer from IAM role permissions what a resource accesses at runtime."""
        edges: list[RuntimeEdge] = []
        iam_roles = [r for r in graph.resources.values() if r.canonical_type is CanonicalResourceType.IAM_ROLE]

        for role in iam_roles:
            # Check which compute resources use this role
            role_users = [r for r in graph.resources.values() if role.id in r.depends_on]
            policy_str = str(role.native_attributes)

            permission_targets: list[tuple[RuntimeCallType, str]] = []
            if "s3:" in policy_str:
                permission_targets.append((RuntimeCallType.STORAGE, "s3"))
            if "dynamodb:" in policy_str:
                permission_targets.append((RuntimeCallType.DATABASE, "dynamodb"))
            if "sqs:" in policy_str:
                permission_targets.append((RuntimeCallType.QUEUE, "sqs"))
            if "sns:" in policy_str:
                permission_targets.append((RuntimeCallType.QUEUE, "sns"))
            if "secretsmanager:" in policy_str:
                permission_targets.append((RuntimeCallType.IAM, "secrets_manager"))

            for caller in role_users:
                for call_type, service in permission_targets:
                    # Find matching resources
                    for target in graph.resources.values():
                        if target.id == caller.id:
                            continue
                        is_storage_match = (
                            call_type == RuntimeCallType.STORAGE
                            and target.canonical_type is CanonicalResourceType.STORAGE_OBJECT_BUCKET
                        )
                        is_db_match = (
                            call_type == RuntimeCallType.DATABASE
                            and target.canonical_type is CanonicalResourceType.DATABASE_NOSQL
                        )
                        if is_storage_match or is_db_match:
                            edges.append(RuntimeEdge(
                                caller_id=caller.id, callee_id=target.id,
                                call_type=call_type, confidence=0.75,
                                evidence=f"IAM role {role.name} has {service} permissions",
                            ))

        return edges
