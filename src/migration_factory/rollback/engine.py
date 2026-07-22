"""Rollback Planner.

Generates a structured rollback plan for every migration: what to do if
deployment fails, in what order, with risk assessment and state restoration
steps. The rollback plan is generated deterministically from the canonical
graph's destroy order and the translation report.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.domain.enums import CanonicalResourceType
from migration_factory.translation.models import TranslationReport

logger = get_logger(__name__)


class RollbackStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_number: int
    resource_id: str
    resource_name: str
    action: str
    description: str
    risk: str
    verification: str


class RollbackPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_steps: int
    estimated_duration_minutes: int
    risk_assessment: str
    pre_rollback_checks: list[str] = Field(default_factory=list)
    rollback_steps: list[RollbackStep] = Field(default_factory=list)
    post_rollback_verification: list[str] = Field(default_factory=list)
    state_restoration: list[str] = Field(default_factory=list)
    terraform_destroy_order: list[str] = Field(default_factory=list)


_ROLLBACK_DURATION_MINUTES: dict[CanonicalResourceType, int] = {
    CanonicalResourceType.NETWORK_VPC: 2,
    CanonicalResourceType.NETWORK_SUBNET: 1,
    CanonicalResourceType.NETWORK_FIREWALL_RULE: 1,
    CanonicalResourceType.NETWORK_NAT_GATEWAY: 3,
    CanonicalResourceType.NETWORK_VPN: 5,
    CanonicalResourceType.NETWORK_PEERING: 2,
    CanonicalResourceType.NETWORK_ROUTE_TABLE: 1,
    CanonicalResourceType.COMPUTE_INSTANCE: 3,
    CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER: 10,
    CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION: 1,
    CanonicalResourceType.COMPUTE_CONTAINER_SERVICE: 5,
    CanonicalResourceType.STORAGE_OBJECT_BUCKET: 2,
    CanonicalResourceType.STORAGE_BLOCK_VOLUME: 2,
    CanonicalResourceType.STORAGE_FILE_SYSTEM: 5,
    CanonicalResourceType.DATABASE_INSTANCE: 15,
    CanonicalResourceType.DATABASE_NOSQL: 10,
    CanonicalResourceType.DATABASE_CACHE: 5,
    CanonicalResourceType.IAM_ROLE: 1,
    CanonicalResourceType.IAM_POLICY: 1,
    CanonicalResourceType.SECRETS_MANAGER: 1,
    CanonicalResourceType.CERTIFICATE: 1,
    CanonicalResourceType.LOAD_BALANCER: 3,
    CanonicalResourceType.CDN_DISTRIBUTION: 5,
    CanonicalResourceType.DNS_ZONE: 2,
    CanonicalResourceType.DNS_RECORD: 1,
    CanonicalResourceType.MESSAGING_TOPIC: 1,
    CanonicalResourceType.MESSAGING_QUEUE: 1,
    CanonicalResourceType.MONITORING_ALARM: 1,
    CanonicalResourceType.LOG_GROUP: 1,
}


@dataclass(slots=True)
class RollbackPlanner:

    def plan(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
    ) -> RollbackPlan:
        translation_index = {tr.resource_id: tr for tr in translation.results}

        # Destroy order = reverse topological
        try:
            destroy_order = graph.destroy_order()
        except Exception:
            destroy_order = list(graph.resources.keys())

        steps: list[RollbackStep] = []
        total_duration = 0

        for i, resource_id in enumerate(destroy_order, 1):
            resource = graph.resources.get(resource_id)
            if resource is None:
                continue

            tr = translation_index.get(resource_id)
            target_service = tr.target_service if tr else "unknown"

            duration = _ROLLBACK_DURATION_MINUTES.get(resource.canonical_type, 2)
            total_duration += duration

            has_state = resource.canonical_type in {
                CanonicalResourceType.DATABASE_INSTANCE,
                CanonicalResourceType.DATABASE_NOSQL,
                CanonicalResourceType.DATABASE_CACHE,
                CanonicalResourceType.STORAGE_OBJECT_BUCKET,
                CanonicalResourceType.STORAGE_FILE_SYSTEM,
            }

            risk = "HIGH — contains persistent data" if has_state else "LOW — stateless resource"

            steps.append(RollbackStep(
                step_number=i,
                resource_id=resource_id,
                resource_name=resource.name,
                action=f"terraform destroy -target={target_service}" if tr else "manual removal",
                description=f"Remove migrated {resource.canonical_type.value}: {resource.name}",
                risk=risk,
                verification=f"Verify {resource.name} is removed and source resource is operational",
            ))

        # Risk assessment
        stateful_count = sum(
            1 for s in steps if "persistent data" in s.risk
        )
        if stateful_count > 2:
            risk_assessment = "HIGH — multiple stateful resources require careful data preservation during rollback"
        elif stateful_count > 0:
            risk_assessment = "MEDIUM — stateful resources present; ensure data backups before rollback"
        else:
            risk_assessment = "LOW — all resources are stateless; rollback is straightforward"

        plan = RollbackPlan(
            total_steps=len(steps),
            estimated_duration_minutes=total_duration,
            risk_assessment=risk_assessment,
            pre_rollback_checks=[
                "Verify source infrastructure is still operational",
                "Ensure DNS/traffic has not been fully cut over to target",
                "Back up any data written to target resources since migration",
                "Notify stakeholders of impending rollback",
                "Confirm rollback window with operations team",
            ],
            rollback_steps=steps,
            post_rollback_verification=[
                "Verify all source resources are healthy and serving traffic",
                "Confirm monitoring alerts are active on source infrastructure",
                "Validate application connectivity through source infrastructure",
                "Check for any data that needs to be synced back from target",
                "Document rollback reason and lessons learned",
            ],
            state_restoration=[
                "Re-import source Terraform state if it was modified during migration",
                "Verify source state matches actual deployed resources",
                "Run terraform plan on source to confirm no drift",
                "Remove any temporary migration resources (peering, VPN, sync agents)",
            ],
            terraform_destroy_order=destroy_order,
        )

        logger.info(
            "rollback_plan_generated",
            total_steps=len(steps),
            estimated_duration=total_duration,
            risk=risk_assessment,
        )
        return plan
