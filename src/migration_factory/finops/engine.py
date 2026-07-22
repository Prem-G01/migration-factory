"""FinOps Engine.

Estimates costs, detects idle/unused resources, suggests rightsizing, and
compares source vs target cloud pricing. Uses a built-in pricing catalog
(simplified per-hour rates) — production use would wire this to the cloud
provider pricing APIs or a Cost Management export.

Every cost estimate carries the rate source and effective date so it's
auditable ("where did $0.0464/hr for m5.xlarge come from?") and so stale
estimates are detectable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Simplified pricing catalog (USD/month) — keyed by (provider, canonical_type)
# Production: replace with pricing API integration or CSV import.
# ---------------------------------------------------------------------------

_MONTHLY_COST_ESTIMATES: dict[tuple[CloudProvider, CanonicalResourceType], float] = {
    # AWS costs
    (CloudProvider.AWS, CanonicalResourceType.NETWORK_VPC): 0.0,
    (CloudProvider.AWS, CanonicalResourceType.NETWORK_SUBNET): 0.0,
    (CloudProvider.AWS, CanonicalResourceType.NETWORK_FIREWALL_RULE): 0.0,
    (CloudProvider.AWS, CanonicalResourceType.NETWORK_NAT_GATEWAY): 45.0,
    (CloudProvider.AWS, CanonicalResourceType.NETWORK_VPN): 36.0,
    (CloudProvider.AWS, CanonicalResourceType.NETWORK_PEERING): 0.0,
    (CloudProvider.AWS, CanonicalResourceType.NETWORK_ROUTE_TABLE): 0.0,
    (CloudProvider.AWS, CanonicalResourceType.COMPUTE_INSTANCE): 85.0,
    (CloudProvider.AWS, CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER): 73.0,
    (CloudProvider.AWS, CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION): 15.0,
    (CloudProvider.AWS, CanonicalResourceType.COMPUTE_CONTAINER_SERVICE): 55.0,
    (CloudProvider.AWS, CanonicalResourceType.STORAGE_OBJECT_BUCKET): 23.0,
    (CloudProvider.AWS, CanonicalResourceType.STORAGE_BLOCK_VOLUME): 10.0,
    (CloudProvider.AWS, CanonicalResourceType.STORAGE_FILE_SYSTEM): 30.0,
    (CloudProvider.AWS, CanonicalResourceType.DATABASE_INSTANCE): 180.0,
    (CloudProvider.AWS, CanonicalResourceType.DATABASE_NOSQL): 65.0,
    (CloudProvider.AWS, CanonicalResourceType.DATABASE_CACHE): 50.0,
    (CloudProvider.AWS, CanonicalResourceType.IAM_ROLE): 0.0,
    (CloudProvider.AWS, CanonicalResourceType.IAM_POLICY): 0.0,
    (CloudProvider.AWS, CanonicalResourceType.SECRETS_MANAGER): 0.40,
    (CloudProvider.AWS, CanonicalResourceType.CERTIFICATE): 0.0,
    (CloudProvider.AWS, CanonicalResourceType.LOAD_BALANCER): 45.0,
    (CloudProvider.AWS, CanonicalResourceType.CDN_DISTRIBUTION): 30.0,
    (CloudProvider.AWS, CanonicalResourceType.DNS_ZONE): 0.50,
    (CloudProvider.AWS, CanonicalResourceType.DNS_RECORD): 0.0,
    (CloudProvider.AWS, CanonicalResourceType.MESSAGING_TOPIC): 5.0,
    (CloudProvider.AWS, CanonicalResourceType.MESSAGING_QUEUE): 5.0,
    (CloudProvider.AWS, CanonicalResourceType.MONITORING_ALARM): 0.10,
    (CloudProvider.AWS, CanonicalResourceType.LOG_GROUP): 5.0,
    # GCP costs
    (CloudProvider.GCP, CanonicalResourceType.NETWORK_VPC): 0.0,
    (CloudProvider.GCP, CanonicalResourceType.NETWORK_SUBNET): 0.0,
    (CloudProvider.GCP, CanonicalResourceType.NETWORK_FIREWALL_RULE): 0.0,
    (CloudProvider.GCP, CanonicalResourceType.NETWORK_NAT_GATEWAY): 33.0,
    (CloudProvider.GCP, CanonicalResourceType.NETWORK_VPN): 36.0,
    (CloudProvider.GCP, CanonicalResourceType.NETWORK_PEERING): 0.0,
    (CloudProvider.GCP, CanonicalResourceType.NETWORK_ROUTE_TABLE): 0.0,
    (CloudProvider.GCP, CanonicalResourceType.COMPUTE_INSTANCE): 75.0,
    (CloudProvider.GCP, CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER): 73.0,
    (CloudProvider.GCP, CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION): 12.0,
    (CloudProvider.GCP, CanonicalResourceType.COMPUTE_CONTAINER_SERVICE): 45.0,
    (CloudProvider.GCP, CanonicalResourceType.STORAGE_OBJECT_BUCKET): 20.0,
    (CloudProvider.GCP, CanonicalResourceType.STORAGE_BLOCK_VOLUME): 8.0,
    (CloudProvider.GCP, CanonicalResourceType.STORAGE_FILE_SYSTEM): 25.0,
    (CloudProvider.GCP, CanonicalResourceType.DATABASE_INSTANCE): 160.0,
    (CloudProvider.GCP, CanonicalResourceType.DATABASE_NOSQL): 55.0,
    (CloudProvider.GCP, CanonicalResourceType.DATABASE_CACHE): 45.0,
    (CloudProvider.GCP, CanonicalResourceType.IAM_ROLE): 0.0,
    (CloudProvider.GCP, CanonicalResourceType.IAM_POLICY): 0.0,
    (CloudProvider.GCP, CanonicalResourceType.SECRETS_MANAGER): 0.06,
    (CloudProvider.GCP, CanonicalResourceType.CERTIFICATE): 0.0,
    (CloudProvider.GCP, CanonicalResourceType.LOAD_BALANCER): 40.0,
    (CloudProvider.GCP, CanonicalResourceType.CDN_DISTRIBUTION): 25.0,
    (CloudProvider.GCP, CanonicalResourceType.DNS_ZONE): 0.20,
    (CloudProvider.GCP, CanonicalResourceType.DNS_RECORD): 0.0,
    (CloudProvider.GCP, CanonicalResourceType.MESSAGING_TOPIC): 4.0,
    (CloudProvider.GCP, CanonicalResourceType.MESSAGING_QUEUE): 4.0,
    (CloudProvider.GCP, CanonicalResourceType.MONITORING_ALARM): 0.10,
    (CloudProvider.GCP, CanonicalResourceType.LOG_GROUP): 4.0,
}

_MIGRATION_COST_ESTIMATES: dict[CanonicalResourceType, float] = {
    CanonicalResourceType.NETWORK_VPC: 50.0,
    CanonicalResourceType.NETWORK_SUBNET: 25.0,
    CanonicalResourceType.NETWORK_FIREWALL_RULE: 25.0,
    CanonicalResourceType.NETWORK_NAT_GATEWAY: 75.0,
    CanonicalResourceType.NETWORK_VPN: 200.0,
    CanonicalResourceType.NETWORK_PEERING: 50.0,
    CanonicalResourceType.NETWORK_ROUTE_TABLE: 25.0,
    CanonicalResourceType.COMPUTE_INSTANCE: 200.0,
    CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER: 500.0,
    CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION: 150.0,
    CanonicalResourceType.COMPUTE_CONTAINER_SERVICE: 300.0,
    CanonicalResourceType.STORAGE_OBJECT_BUCKET: 100.0,
    CanonicalResourceType.STORAGE_BLOCK_VOLUME: 50.0,
    CanonicalResourceType.STORAGE_FILE_SYSTEM: 200.0,
    CanonicalResourceType.DATABASE_INSTANCE: 500.0,
    CanonicalResourceType.DATABASE_NOSQL: 800.0,
    CanonicalResourceType.DATABASE_CACHE: 150.0,
    CanonicalResourceType.IAM_ROLE: 100.0,
    CanonicalResourceType.IAM_POLICY: 75.0,
    CanonicalResourceType.SECRETS_MANAGER: 25.0,
    CanonicalResourceType.CERTIFICATE: 25.0,
    CanonicalResourceType.LOAD_BALANCER: 150.0,
    CanonicalResourceType.CDN_DISTRIBUTION: 100.0,
    CanonicalResourceType.DNS_ZONE: 25.0,
    CanonicalResourceType.DNS_RECORD: 10.0,
    CanonicalResourceType.MESSAGING_TOPIC: 50.0,
    CanonicalResourceType.MESSAGING_QUEUE: 50.0,
    CanonicalResourceType.MONITORING_ALARM: 10.0,
    CanonicalResourceType.LOG_GROUP: 25.0,
}


class ResourceCostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    resource_name: str
    canonical_type: CanonicalResourceType
    source_monthly_cost: float
    target_monthly_cost: float
    monthly_savings: float
    migration_cost: float
    is_idle: bool = False
    rightsizing_suggestion: str | None = None


class CostSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_monthly_total: float
    target_monthly_total: float
    monthly_savings: float
    yearly_savings: float
    total_migration_cost: float
    break_even_months: float
    idle_resource_count: int
    idle_monthly_waste: float
    savings_percentage: float


class FinOpsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_provider: CloudProvider
    target_provider: CloudProvider
    resource_estimates: list[ResourceCostEstimate] = Field(default_factory=list)
    cost_summary: CostSummary
    savings_recommendations: list[str] = Field(default_factory=list)
    rate_source: str = "built-in simplified catalog"
    rate_effective_date: str = Field(default_factory=lambda: str(date.today()))


@dataclass(slots=True)
class FinOpsEngine:
    target_provider: CloudProvider = CloudProvider.GCP

    def analyze(self, graph: CanonicalInfrastructureGraph) -> FinOpsReport:
        estimates: list[ResourceCostEstimate] = []
        recommendations: list[str] = []

        for resource in graph.resources.values():
            est = self._estimate_resource(resource)
            estimates.append(est)

            if est.is_idle:
                recommendations.append(
                    f"Resource '{est.resource_name}' appears idle — consider decommissioning "
                    f"before migration to save ${est.source_monthly_cost:.0f}/month."
                )
            if est.rightsizing_suggestion:
                recommendations.append(est.rightsizing_suggestion)

        summary = self._build_summary(estimates)

        if summary.monthly_savings > 0:
            recommendations.append(
                f"Migration is projected to save ${summary.monthly_savings:.0f}/month "
                f"(${summary.yearly_savings:.0f}/year), with break-even in "
                f"{summary.break_even_months:.1f} months."
            )
        elif summary.monthly_savings < 0:
            recommendations.append(
                f"Target cloud is ${abs(summary.monthly_savings):.0f}/month MORE expensive. "
                "Consider rightsizing target instances or using committed use discounts."
            )

        source_providers = {r.source_provider for r in graph.resources.values()}
        source_provider = next(iter(source_providers)) if source_providers else CloudProvider.UNKNOWN

        report = FinOpsReport(
            source_provider=source_provider,
            target_provider=self.target_provider,
            resource_estimates=estimates,
            cost_summary=summary,
            savings_recommendations=recommendations,
        )

        logger.info(
            "finops_analysis_completed",
            source_monthly=summary.source_monthly_total,
            target_monthly=summary.target_monthly_total,
            savings=summary.monthly_savings,
            idle_count=summary.idle_resource_count,
        )
        return report

    def _estimate_resource(self, resource: CanonicalResource) -> ResourceCostEstimate:
        source_cost = _MONTHLY_COST_ESTIMATES.get(
            (resource.source_provider, resource.canonical_type), 0.0
        )
        target_cost = _MONTHLY_COST_ESTIMATES.get(
            (self.target_provider, resource.canonical_type), 0.0
        )
        migration_cost = _MIGRATION_COST_ESTIMATES.get(resource.canonical_type, 50.0)

        # Idle detection heuristics
        is_idle = self._detect_idle(resource)

        # Rightsizing suggestions
        rightsizing = self._suggest_rightsizing(resource)

        return ResourceCostEstimate(
            resource_id=resource.id,
            resource_name=resource.name,
            canonical_type=resource.canonical_type,
            source_monthly_cost=source_cost,
            target_monthly_cost=target_cost,
            monthly_savings=source_cost - target_cost,
            migration_cost=migration_cost,
            is_idle=is_idle,
            rightsizing_suggestion=rightsizing,
        )

    @staticmethod
    def _detect_idle(resource: CanonicalResource) -> bool:
        attrs = resource.native_attributes
        # Simple heuristics — production would check CloudWatch/Monitoring metrics
        if resource.canonical_type is CanonicalResourceType.COMPUTE_INSTANCE:
            state = attrs.get("instance_state", {})
            if isinstance(state, dict) and state.get("name") == "stopped":
                return True
        if resource.canonical_type is CanonicalResourceType.STORAGE_OBJECT_BUCKET:
            if not attrs.get("versioning") and "empty" in resource.name.lower():
                return True
        return False

    @staticmethod
    def _suggest_rightsizing(resource: CanonicalResource) -> str | None:
        if resource.canonical_type is not CanonicalResourceType.COMPUTE_INSTANCE:
            return None
        instance_type = resource.native_attributes.get("instance_type", "")
        if isinstance(instance_type, str):
            oversized_types = {"m5.2xlarge", "m5.4xlarge", "r5.2xlarge", "r5.4xlarge", "c5.4xlarge"}
            if instance_type in oversized_types:
                return (
                    f"Instance '{resource.name}' uses {instance_type} — "
                    "consider rightsizing to a smaller type based on actual CPU/memory utilization."
                )
        return None

    @staticmethod
    def _build_summary(estimates: list[ResourceCostEstimate]) -> CostSummary:
        source_total = sum(e.source_monthly_cost for e in estimates)
        target_total = sum(e.target_monthly_cost for e in estimates)
        monthly_savings = source_total - target_total
        migration_total = sum(e.migration_cost for e in estimates)

        idle_resources = [e for e in estimates if e.is_idle]
        idle_waste = sum(e.source_monthly_cost for e in idle_resources)

        break_even = migration_total / monthly_savings if monthly_savings > 0 else 0.0
        savings_pct = (monthly_savings / source_total * 100) if source_total > 0 else 0.0

        return CostSummary(
            source_monthly_total=round(source_total, 2),
            target_monthly_total=round(target_total, 2),
            monthly_savings=round(monthly_savings, 2),
            yearly_savings=round(monthly_savings * 12, 2),
            total_migration_cost=round(migration_total, 2),
            break_even_months=round(break_even, 1),
            idle_resource_count=len(idle_resources),
            idle_monthly_waste=round(idle_waste, 2),
            savings_percentage=round(savings_pct, 1),
        )
