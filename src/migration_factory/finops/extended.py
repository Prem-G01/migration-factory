"""FinOps extensions: network egress cost analysis, storage optimization."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.domain.enums import CanonicalResourceType

logger = get_logger(__name__)


class NetworkCostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inter_region_egress_gb: float = 0
    internet_egress_gb: float = 0
    estimated_egress_cost: float = 0
    migration_transfer_gb: float = 0
    migration_transfer_cost: float = 0
    recommendations: list[str] = Field(default_factory=list)


class StorageOptimization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_buckets: int = 0
    missing_lifecycle_policy: list[str] = Field(default_factory=list)
    wrong_storage_class: list[str] = Field(default_factory=list)
    estimated_savings_monthly: float = 0
    recommendations: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class NetworkCostAnalyzer:
    """Estimates network egress and data transfer costs for migration."""

    egress_cost_per_gb: float = 0.08  # avg cross-cloud egress $/GB
    transfer_cost_per_gb: float = 0.02  # managed transfer service $/GB

    def analyze(self, graph: CanonicalInfrastructureGraph) -> NetworkCostEstimate:
        recs: list[str] = []
        transfer_gb = 0.0

        for resource in graph.resources.values():
            attrs = resource.native_attributes

            if resource.canonical_type is CanonicalResourceType.STORAGE_OBJECT_BUCKET:
                # Estimate bucket size from tags or assume 100GB default
                size_gb = float(attrs.get("size_gb", 100))
                transfer_gb += size_gb

            if resource.canonical_type is CanonicalResourceType.DATABASE_INSTANCE:
                # Estimate DB size
                allocated = float(attrs.get("allocated_storage", 50))
                transfer_gb += allocated

            if resource.canonical_type is CanonicalResourceType.STORAGE_FILE_SYSTEM:
                size = float(attrs.get("size_in_bytes", 50 * 1024**3)) / (1024**3)
                transfer_gb += size

        egress_cost = transfer_gb * self.egress_cost_per_gb
        transfer_cost = transfer_gb * self.transfer_cost_per_gb

        if transfer_gb > 1000:
            recs.append(f"Large transfer ({transfer_gb:.0f} GB): consider using a physical transfer appliance")
        if transfer_gb > 100:
            recs.append("Use managed transfer services (Storage Transfer Service, DMS) for reliability")
        recs.append("Schedule transfers during off-peak hours to minimize impact")

        return NetworkCostEstimate(
            migration_transfer_gb=round(transfer_gb, 1),
            migration_transfer_cost=round(transfer_cost, 2),
            estimated_egress_cost=round(egress_cost, 2),
            recommendations=recs,
        )


@dataclass(slots=True)
class StorageOptimizer:
    """Identifies storage optimization opportunities."""

    def analyze(self, graph: CanonicalInfrastructureGraph) -> StorageOptimization:
        buckets = [r for r in graph.resources.values() if r.canonical_type is CanonicalResourceType.STORAGE_OBJECT_BUCKET]
        missing_lifecycle: list[str] = []
        wrong_class: list[str] = []
        recs: list[str] = []
        savings = 0.0

        for bucket in buckets:
            attrs = bucket.native_attributes
            if not attrs.get("lifecycle_rule") and not attrs.get("lifecycle_configuration"):
                missing_lifecycle.append(bucket.name)
                savings += 5.0  # estimated savings from adding lifecycle

            storage_class = str(attrs.get("storage_class", "STANDARD")).upper()
            if storage_class == "STANDARD":
                wrong_class.append(f"{bucket.name}: consider NEARLINE/COLDLINE for infrequently accessed data")
                savings += 3.0

        if missing_lifecycle:
            recs.append(f"{len(missing_lifecycle)} buckets lack lifecycle policies — add auto-transition to cold storage")
        if wrong_class:
            recs.append("Review storage classes: STANDARD may be over-provisioned for archive data")
        if buckets:
            recs.append("Enable object versioning with lifecycle cleanup to prevent unbounded version growth")

        return StorageOptimization(
            total_buckets=len(buckets),
            missing_lifecycle_policy=missing_lifecycle,
            wrong_storage_class=wrong_class,
            estimated_savings_monthly=round(savings, 2),
            recommendations=recs,
        )
