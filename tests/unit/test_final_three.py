"""Tests for app_graph, runtime_graph, and multi_tenant modules."""

from __future__ import annotations

from migration_factory.dependency.app_graph import AppDependencyGraphBuilder, AppDependencyType
from migration_factory.dependency.runtime_graph import RuntimeCallType, RuntimeDependencyGraphBuilder
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph, CanonicalResource, SourceLocation
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.platform.multi_tenant import (
    AuditLog,
    Permission,
    TenantConfig,
    TenantContext,
    TenantRegistry,
    TenantRole,
    TenantUser,
)


def _loc():
    return SourceLocation(source_system="test", source_path="test")


def _resource(rid, ctype, depends_on=frozenset(), tags=None, application=None, owner=None, criticality=None, **attrs):
    r = CanonicalResource(
        id=rid, canonical_type=ctype, source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}", name=rid,
        depends_on=depends_on, tags=tags or {}, native_attributes=attrs,
        source_location=_loc(), application=application, owner=owner, criticality=criticality,
    )
    return r


def _sample_multi_app_graph():
    g = CanonicalInfrastructureGraph()
    g.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
    g.add_resource(_resource("subnet", CanonicalResourceType.NETWORK_SUBNET, depends_on=frozenset({"vpc"})))
    g.add_resource(_resource("api-server", CanonicalResourceType.COMPUTE_INSTANCE,
        depends_on=frozenset({"subnet"}), application="web-api", owner="platform", criticality="high"))
    g.add_resource(_resource("worker", CanonicalResourceType.COMPUTE_INSTANCE,
        depends_on=frozenset({"subnet"}), application="worker-service", owner="data-team"))
    g.add_resource(_resource("shared-db", CanonicalResourceType.DATABASE_INSTANCE,
        depends_on=frozenset({"subnet"}), application="web-api"))
    g.add_resource(_resource("shared-queue", CanonicalResourceType.MESSAGING_QUEUE))
    g.add_resource(_resource("api-bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET,
        application="web-api"))
    return g


# --- Application Dependency Graph ---

class TestAppDependencyGraph:
    def test_groups_resources_by_app(self):
        graph = _sample_multi_app_graph()
        app_graph = AppDependencyGraphBuilder().build(graph)
        assert "web-api" in app_graph.apps
        assert "worker-service" in app_graph.apps

    def test_ungrouped_resources_reported(self):
        graph = _sample_multi_app_graph()
        app_graph = AppDependencyGraphBuilder().build(graph)
        assert len(app_graph.ungrouped_resources) > 0

    def test_criticality_aggregated(self):
        graph = _sample_multi_app_graph()
        app_graph = AppDependencyGraphBuilder().build(graph)
        assert app_graph.apps["web-api"].criticality == "high"

    def test_migration_order_computed(self):
        graph = _sample_multi_app_graph()
        app_graph = AppDependencyGraphBuilder().build(graph)
        order = app_graph.migration_order()
        assert len(order) == len(app_graph.apps)

    def test_tag_declared_dependency(self):
        g = CanonicalInfrastructureGraph()
        r1 = _resource("svc-a", CanonicalResourceType.COMPUTE_INSTANCE,
                        tags={"Application": "svc-a", "upstream-service": "svc-b"},
                        application="svc-a")
        r2 = _resource("svc-b", CanonicalResourceType.COMPUTE_INSTANCE,
                        tags={"Application": "svc-b"}, application="svc-b")
        g.add_resource(r1)
        g.add_resource(r2)
        app_graph = AppDependencyGraphBuilder().build(g)
        tag_edges = [e for e in app_graph.edges if e.dependency_type is AppDependencyType.TAG_DECLARED]
        assert len(tag_edges) == 1

    def test_name_inference(self):
        from migration_factory.dependency.app_graph import AppDependencyGraphBuilder
        builder = AppDependencyGraphBuilder()
        assert builder._infer_app_from_name("payments-db") == "payments"
        assert builder._infer_app_from_name("prod-auth-server") == "auth"
        assert builder._infer_app_from_name("main") is None

    def test_get_dependencies_of(self):
        graph = _sample_multi_app_graph()
        app_graph = AppDependencyGraphBuilder().build(graph)
        deps = app_graph.get_dependencies_of("web-api")
        assert isinstance(deps, list)

    def test_app_node_resource_count(self):
        graph = _sample_multi_app_graph()
        app_graph = AppDependencyGraphBuilder().build(graph)
        assert app_graph.apps["web-api"].resource_count >= 2


# --- Runtime Dependency Graph ---

class TestRuntimeDependencyGraph:
    def test_builds_from_graph(self):
        graph = _sample_multi_app_graph()
        rtg = RuntimeDependencyGraphBuilder().build(graph)
        assert isinstance(rtg.edges, list)

    def test_infers_from_colocation(self):
        g = CanonicalInfrastructureGraph()
        g.add_resource(_resource("compute", CanonicalResourceType.COMPUTE_INSTANCE,
            subnet_id="subnet-123"))
        g.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE,
            subnet_id="subnet-123"))
        rtg = RuntimeDependencyGraphBuilder().build(g)
        db_edges = [e for e in rtg.edges if e.callee_id == "db"]
        assert len(db_edges) >= 1
        assert db_edges[0].call_type is RuntimeCallType.DATABASE

    def test_infers_from_sg_ports(self):
        g = CanonicalInfrastructureGraph()
        g.add_resource(_resource("sg", CanonicalResourceType.NETWORK_FIREWALL_RULE,
            ingress=[{"from_port": 5432, "to_port": 5432, "cidr_blocks": ["10.0.0.0/8"]}]))
        g.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE,
            depends_on=frozenset({"sg"})))
        rtg = RuntimeDependencyGraphBuilder().build(g)
        pg_edges = [e for e in rtg.edges if e.protocol == "PostgreSQL"]
        assert len(pg_edges) >= 1

    def test_infers_from_iam(self):
        g = CanonicalInfrastructureGraph()
        role = _resource("app-role", CanonicalResourceType.IAM_ROLE,
            managed_policy_arns=["arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"],
            inline_policy={"Statement": [{"Action": ["s3:GetObject"], "Effect": "Allow"}]})
        compute = _resource("app", CanonicalResourceType.COMPUTE_INSTANCE,
            depends_on=frozenset({"app-role"}))
        bucket = _resource("data-bucket", CanonicalResourceType.STORAGE_OBJECT_BUCKET)
        g.add_resource(role)
        g.add_resource(compute)
        g.add_resource(bucket)
        rtg = RuntimeDependencyGraphBuilder().build(g)
        storage_edges = [e for e in rtg.edges if e.call_type is RuntimeCallType.STORAGE]
        assert len(storage_edges) >= 1

    def test_high_confidence_edges(self):
        g = CanonicalInfrastructureGraph()
        compute = _resource("fn", CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION,
            environment={"variables": {"DB_HOST": "my-db", "REDIS_URL": "redis://cache"}})
        db = _resource("my-db", CanonicalResourceType.DATABASE_INSTANCE)
        g.add_resource(compute)
        g.add_resource(db)
        rtg = RuntimeDependencyGraphBuilder().build(g)
        high_conf = rtg.high_confidence_edges
        assert len(high_conf) >= 1

    def test_callers_and_callees(self):
        g = CanonicalInfrastructureGraph()
        g.add_resource(_resource("compute", CanonicalResourceType.COMPUTE_INSTANCE, subnet_id="sub-1"))
        g.add_resource(_resource("db", CanonicalResourceType.DATABASE_INSTANCE, subnet_id="sub-1"))
        rtg = RuntimeDependencyGraphBuilder().build(g)
        callers = rtg.callers_of("db")
        assert isinstance(callers, list)


# --- Multi-Tenant Platform ---

class TestMultiTenant:
    def test_create_tenant(self):
        registry = TenantRegistry()
        config = TenantConfig(tenant_id="t1", tenant_name="Acme Corp")
        ctx = registry.create_tenant(config)
        assert ctx.config.tenant_id == "t1"

    def test_cannot_create_duplicate_tenant(self):
        registry = TenantRegistry()
        config = TenantConfig(tenant_id="t1", tenant_name="Acme")
        registry.create_tenant(config)
        import pytest
        with pytest.raises(ValueError, match="already exists"):
            registry.create_tenant(config)

    def test_get_tenant(self):
        registry = TenantRegistry()
        config = TenantConfig(tenant_id="t2", tenant_name="Beta Inc")
        registry.create_tenant(config)
        ctx = registry.get_tenant("t2")
        assert ctx.config.tenant_name == "Beta Inc"

    def test_rbac_owner_has_all_permissions(self):
        user = TenantUser(user_id="u1", email="owner@test.com", role=TenantRole.OWNER)
        for perm in Permission:
            assert user.has_permission(perm)

    def test_rbac_viewer_read_only(self):
        user = TenantUser(user_id="u2", email="viewer@test.com", role=TenantRole.VIEWER)
        assert user.has_permission(Permission.READ_GRAPH)
        assert not user.has_permission(Permission.EXECUTE_MIGRATION)
        assert not user.has_permission(Permission.MANAGE_USERS)

    def test_rbac_engineer_cannot_manage_users(self):
        user = TenantUser(user_id="u3", email="eng@test.com", role=TenantRole.ENGINEER)
        assert user.has_permission(Permission.WRITE_GRAPH)
        assert not user.has_permission(Permission.MANAGE_USERS)

    def test_graph_store_and_retrieve(self):
        registry = TenantRegistry()
        ctx = registry.create_tenant(TenantConfig(tenant_id="t3", tenant_name="Test"))
        owner = TenantUser(user_id="owner", email="o@test.com", role=TenantRole.OWNER)
        ctx.add_user(owner)
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        ctx.store_graph("g1", graph, "owner")
        retrieved = ctx.get_graph("g1", "owner")
        assert len(retrieved.resources) == 1

    def test_unauthorized_write_raises(self):
        registry = TenantRegistry()
        ctx = registry.create_tenant(TenantConfig(tenant_id="t4", tenant_name="Test"))
        viewer = TenantUser(user_id="viewer", email="v@test.com", role=TenantRole.VIEWER)
        ctx.add_user(viewer)
        graph = CanonicalInfrastructureGraph()
        import pytest
        with pytest.raises(PermissionError):
            ctx.store_graph("g1", graph, "viewer")

    def test_audit_log_records_events(self):
        log = AuditLog()
        log.log("t1", "u1", "graph.stored", graph_id="g1")
        log.log("t1", "u2", "assessment.run")
        events = log.events_for_tenant("t1")
        assert len(events) == 2

    def test_audit_log_user_filter(self):
        log = AuditLog()
        log.log("t1", "u1", "action.a")
        log.log("t1", "u2", "action.b")
        log.log("t1", "u1", "action.c")
        user_events = log.events_for_user("t1", "u1")
        assert len(user_events) == 2

    def test_policy_parameters_from_config(self):
        config = TenantConfig(
            tenant_id="t5", tenant_name="Regulated Corp",
            required_tags=["Owner", "CostCenter"],
            allowed_regions=["us-east-1", "us-west-2"],
            naming_prefix="rc-",
        )
        ctx = TenantContext(config=config)
        params = ctx.policy_parameters()
        assert params["required_tags"] == ["Owner", "CostCenter"]
        assert params["allowed_regions"] == ["us-east-1", "us-west-2"]
        assert params["required_prefix"] == "rc-"

    def test_resource_limit_enforced(self):
        config = TenantConfig(tenant_id="t6", tenant_name="Small", max_resources_per_graph=2)
        registry = TenantRegistry()
        ctx = registry.create_tenant(config)
        owner = TenantUser(user_id="o", email="o@t.com", role=TenantRole.OWNER)
        ctx.add_user(owner)
        graph = CanonicalInfrastructureGraph()
        for i in range(3):
            graph.add_resource(_resource(f"r{i}", CanonicalResourceType.NETWORK_VPC))
        import pytest
        with pytest.raises(ValueError, match="exceeds tenant limit"):
            ctx.store_graph("g1", graph, "o")

    def test_list_tenants(self):
        registry = TenantRegistry()
        registry.create_tenant(TenantConfig(tenant_id="a", tenant_name="A"))
        registry.create_tenant(TenantConfig(tenant_id="b", tenant_name="B"))
        assert registry.list_tenants() == ["a", "b"]

    def test_delete_tenant(self):
        registry = TenantRegistry()
        registry.create_tenant(TenantConfig(tenant_id="del", tenant_name="Delete Me"))
        registry.delete_tenant("del")
        import pytest
        with pytest.raises(KeyError):
            registry.get_tenant("del")
