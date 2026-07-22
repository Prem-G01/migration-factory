"""Multi-Tenant Platform Support.

Provides tenant isolation for the Migration Factory when deployed as a
shared service. Each tenant gets:
- Isolated canonical infrastructure graph
- Tenant-scoped configuration overrides
- Per-tenant audit trail
- RBAC (role-based access control) at the tenant level
- Tenant-specific policy packs and capability matrices

Architecture: the platform remains stateless; all tenant data is passed
in via context, not stored globally. This is the correct pattern for a
library/API deployment — a full SaaS platform would add a persistence
layer (PostgreSQL, Redis) and HTTP authentication layer on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


class TenantRole(StrEnum):
    OWNER = "owner"  # Full access: read, write, execute, manage users
    ADMIN = "admin"  # Read, write, execute; cannot manage users
    ENGINEER = "engineer"  # Read, write (no deploy)
    VIEWER = "viewer"  # Read-only
    AUDITOR = "auditor"  # Read-only + audit log access


class Permission(StrEnum):
    READ_GRAPH = "read:graph"
    WRITE_GRAPH = "write:graph"
    EXECUTE_MIGRATION = "execute:migration"
    RUN_ASSESSMENT = "run:assessment"
    GENERATE_TERRAFORM = "generate:terraform"
    VIEW_SECURITY = "view:security"
    MANAGE_POLICIES = "manage:policies"
    VIEW_AUDIT_LOG = "view:audit_log"
    MANAGE_USERS = "manage:users"
    MANAGE_TENANT = "manage:tenant"


_ROLE_PERMISSIONS: dict[TenantRole, set[Permission]] = {
    TenantRole.OWNER: set(Permission),
    TenantRole.ADMIN: {
        Permission.READ_GRAPH, Permission.WRITE_GRAPH, Permission.EXECUTE_MIGRATION,
        Permission.RUN_ASSESSMENT, Permission.GENERATE_TERRAFORM,
        Permission.VIEW_SECURITY, Permission.MANAGE_POLICIES, Permission.VIEW_AUDIT_LOG,
    },
    TenantRole.ENGINEER: {
        Permission.READ_GRAPH, Permission.WRITE_GRAPH,
        Permission.RUN_ASSESSMENT, Permission.GENERATE_TERRAFORM,
        Permission.VIEW_SECURITY,
    },
    TenantRole.VIEWER: {Permission.READ_GRAPH, Permission.RUN_ASSESSMENT},
    TenantRole.AUDITOR: {Permission.READ_GRAPH, Permission.VIEW_AUDIT_LOG},
}


class TenantUser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    email: str
    role: TenantRole
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def has_permission(self, permission: Permission) -> bool:
        return permission in _ROLE_PERMISSIONS.get(self.role, set())


# ---------------------------------------------------------------------------
# Tenant Config
# ---------------------------------------------------------------------------


class TenantConfig(BaseModel):
    """Per-tenant configuration overrides."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    tenant_name: str
    plan: str = "professional"  # starter, professional, enterprise

    # Policy overrides
    required_tags: list[str] = Field(default_factory=list)
    allowed_regions: list[str] = Field(default_factory=list)
    naming_prefix: str = ""
    fail_on_policy_violation: bool = False

    # Feature flags
    ai_enabled: bool = True
    max_resources_per_graph: int = 10000
    max_concurrent_migrations: int = 5

    # Compliance scope
    compliance_frameworks: list[str] = Field(
        default_factory=lambda: ["CIS", "NIST", "SOC2"]
    )


# ---------------------------------------------------------------------------
# Audit Trail
# ---------------------------------------------------------------------------


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    user_id: str
    action: str
    resource_type: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    ip_address: str = ""


class AuditLog:
    """In-memory audit log. Production: persist to append-only storage."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def log(self, tenant_id: str, user_id: str, action: str, **details: Any) -> AuditEvent:
        event = AuditEvent(
            tenant_id=tenant_id, user_id=user_id, action=action, details=details
        )
        self._events.append(event)
        logger.info("audit_event", tenant_id=tenant_id, user_id=user_id, action=action)
        return event

    def events_for_tenant(self, tenant_id: str) -> list[AuditEvent]:
        return [e for e in self._events if e.tenant_id == tenant_id]

    def events_for_user(self, tenant_id: str, user_id: str) -> list[AuditEvent]:
        return [e for e in self._events if e.tenant_id == tenant_id and e.user_id == user_id]


# ---------------------------------------------------------------------------
# Tenant Context
# ---------------------------------------------------------------------------


class TenantContext(BaseModel):
    """A scoped execution context for one tenant."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    config: TenantConfig
    users: dict[str, TenantUser] = Field(default_factory=dict)
    graphs: dict[str, CanonicalInfrastructureGraph] = Field(default_factory=dict)
    audit_log: AuditLog = Field(default_factory=AuditLog)

    def add_user(self, user: TenantUser) -> None:
        self.users[user.user_id] = user

    def authorize(self, user_id: str, permission: Permission) -> bool:
        user = self.users.get(user_id)
        if user is None:
            return False
        return user.has_permission(permission)

    def store_graph(self, graph_id: str, graph: CanonicalInfrastructureGraph, user_id: str) -> None:
        if not self.authorize(user_id, Permission.WRITE_GRAPH):
            raise PermissionError(f"User {user_id} lacks {Permission.WRITE_GRAPH}")
        if len(graph.resources) > self.config.max_resources_per_graph:
            raise ValueError(
                f"Graph exceeds tenant limit of {self.config.max_resources_per_graph} resources"
            )
        self.graphs[graph_id] = graph
        self.audit_log.log(self.config.tenant_id, user_id, "graph.stored", graph_id=graph_id,
                           resource_count=len(graph.resources))

    def get_graph(self, graph_id: str, user_id: str) -> CanonicalInfrastructureGraph:
        if not self.authorize(user_id, Permission.READ_GRAPH):
            raise PermissionError(f"User {user_id} lacks {Permission.READ_GRAPH}")
        if graph_id not in self.graphs:
            raise KeyError(f"Graph {graph_id!r} not found in tenant {self.config.tenant_id!r}")
        self.audit_log.log(self.config.tenant_id, user_id, "graph.accessed", graph_id=graph_id)
        return self.graphs[graph_id]

    def policy_parameters(self) -> dict[str, Any]:
        """Return tenant-specific policy engine parameters."""
        params: dict[str, Any] = {}
        if self.config.required_tags:
            params["required_tags"] = self.config.required_tags
        if self.config.allowed_regions:
            params["allowed_regions"] = self.config.allowed_regions
        if self.config.naming_prefix:
            params["required_prefix"] = self.config.naming_prefix
        return params


# ---------------------------------------------------------------------------
# Tenant Registry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TenantRegistry:
    """Registry of all tenants. Singleton in production, injected in tests."""

    _tenants: dict[str, TenantContext] = field(default_factory=dict)

    def create_tenant(self, config: TenantConfig) -> TenantContext:
        if config.tenant_id in self._tenants:
            raise ValueError(f"Tenant {config.tenant_id!r} already exists")
        ctx = TenantContext(config=config)
        self._tenants[config.tenant_id] = ctx
        logger.info("tenant_created", tenant_id=config.tenant_id, plan=config.plan)
        return ctx

    def get_tenant(self, tenant_id: str) -> TenantContext:
        ctx = self._tenants.get(tenant_id)
        if ctx is None:
            raise KeyError(f"Tenant {tenant_id!r} not found")
        return ctx

    def list_tenants(self) -> list[str]:
        return sorted(self._tenants.keys())

    def delete_tenant(self, tenant_id: str) -> None:
        if tenant_id not in self._tenants:
            raise KeyError(f"Tenant {tenant_id!r} not found")
        del self._tenants[tenant_id]
        logger.info("tenant_deleted", tenant_id=tenant_id)
