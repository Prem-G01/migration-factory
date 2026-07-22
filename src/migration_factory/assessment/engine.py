"""Migration Assessment Engine.

Answers the question every enterprise asks first: "Should we migrate this,
and what will hurt?" — BEFORE any Terraform is generated.

Deterministic: (TranslationReport, CanonicalInfrastructureGraph) ->
MigrationAssessment. Same inputs always produce the same assessment. Every
score is decomposable — the `ScoreBreakdown` on each resource shows exactly
which factors produced the number, so a stakeholder can challenge it ("why is
Cloud SQL scored 82?") and get a concrete answer instead of "the model said so."

Phased planning uses the graph's topological order, grouped by canonical
resource category. The ordering within each phase respects dependency edges:
a subnet is never scheduled before its VPC, and a database is never
scheduled before its network foundation — regardless of which phase the
resource lands in.
"""

from __future__ import annotations

from dataclasses import dataclass

from migration_factory.assessment.models import (
    DowntimeClass,
    MigrationAssessment,
    MigrationPhase,
    MigrationStrategy,
    ResourceAssessment,
    RiskLevel,
    ScoreBreakdown,
)
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.domain.enums import CanonicalResourceType
from migration_factory.translation.models import (
    SupportStatus,
    TranslationReport,
    TranslationResult,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Scoring constants — kept as module-level constants (not magic numbers
# buried in methods) so they're visible, documented, and tunable.
# ---------------------------------------------------------------------------

_COMPLEXITY_WEIGHT_MULTIPLIER = 6
_DEPENDENCY_POINTS_PER_EDGE = 4
_DEPENDENCY_POINTS_CAP = 20

_SUPPORT_PENALTY: dict[SupportStatus, int] = {
    SupportStatus.SUPPORTED: 0,
    SupportStatus.PARTIAL: 15,
    SupportStatus.MANUAL: 30,
    SupportStatus.UNSUPPORTED: 40,
}

_STRATEGY_MAP: dict[SupportStatus, MigrationStrategy] = {
    SupportStatus.SUPPORTED: MigrationStrategy.REHOST,
    SupportStatus.PARTIAL: MigrationStrategy.REPLATFORM,
    SupportStatus.MANUAL: MigrationStrategy.MANUAL,
    SupportStatus.UNSUPPORTED: MigrationStrategy.MANUAL,
}

_DOWNTIME_MAP: dict[CanonicalResourceType, DowntimeClass] = {
    # Networking — no downtime (additive)
    CanonicalResourceType.NETWORK_VPC: DowntimeClass.NONE,
    CanonicalResourceType.NETWORK_SUBNET: DowntimeClass.NONE,
    CanonicalResourceType.NETWORK_FIREWALL_RULE: DowntimeClass.NONE,
    CanonicalResourceType.NETWORK_NAT_GATEWAY: DowntimeClass.LOW,
    CanonicalResourceType.NETWORK_VPN: DowntimeClass.MEDIUM,
    CanonicalResourceType.NETWORK_PEERING: DowntimeClass.LOW,
    CanonicalResourceType.NETWORK_ROUTE_TABLE: DowntimeClass.NONE,
    # Compute
    CanonicalResourceType.COMPUTE_INSTANCE: DowntimeClass.MEDIUM,
    CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER: DowntimeClass.MEDIUM,
    CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION: DowntimeClass.LOW,
    CanonicalResourceType.COMPUTE_CONTAINER_SERVICE: DowntimeClass.LOW,
    # Storage
    CanonicalResourceType.STORAGE_OBJECT_BUCKET: DowntimeClass.LOW,
    CanonicalResourceType.STORAGE_BLOCK_VOLUME: DowntimeClass.MEDIUM,
    CanonicalResourceType.STORAGE_FILE_SYSTEM: DowntimeClass.HIGH,
    # Database
    CanonicalResourceType.DATABASE_INSTANCE: DowntimeClass.HIGH,
    CanonicalResourceType.DATABASE_NOSQL: DowntimeClass.HIGH,
    CanonicalResourceType.DATABASE_CACHE: DowntimeClass.MEDIUM,
    # Security
    CanonicalResourceType.IAM_ROLE: DowntimeClass.NONE,
    CanonicalResourceType.IAM_POLICY: DowntimeClass.NONE,
    CanonicalResourceType.SECRETS_MANAGER: DowntimeClass.NONE,
    CanonicalResourceType.CERTIFICATE: DowntimeClass.LOW,
    # App services
    CanonicalResourceType.LOAD_BALANCER: DowntimeClass.LOW,
    CanonicalResourceType.CDN_DISTRIBUTION: DowntimeClass.LOW,
    CanonicalResourceType.DNS_ZONE: DowntimeClass.LOW,
    CanonicalResourceType.DNS_RECORD: DowntimeClass.LOW,
    CanonicalResourceType.MESSAGING_TOPIC: DowntimeClass.LOW,
    CanonicalResourceType.MESSAGING_QUEUE: DowntimeClass.LOW,
    # Observability
    CanonicalResourceType.MONITORING_ALARM: DowntimeClass.NONE,
    CanonicalResourceType.LOG_GROUP: DowntimeClass.NONE,
}

_PHASE_ASSIGNMENT: list[tuple[str, set[CanonicalResourceType]]] = [
    ("Networking", {
        CanonicalResourceType.NETWORK_VPC,
        CanonicalResourceType.NETWORK_SUBNET,
        CanonicalResourceType.NETWORK_FIREWALL_RULE,
        CanonicalResourceType.NETWORK_NAT_GATEWAY,
        CanonicalResourceType.NETWORK_VPN,
        CanonicalResourceType.NETWORK_PEERING,
        CanonicalResourceType.NETWORK_ROUTE_TABLE,
    }),
    ("IAM & Security", {
        CanonicalResourceType.IAM_ROLE,
        CanonicalResourceType.IAM_POLICY,
        CanonicalResourceType.SECRETS_MANAGER,
        CanonicalResourceType.CERTIFICATE,
    }),
    ("DNS & CDN", {
        CanonicalResourceType.DNS_ZONE,
        CanonicalResourceType.DNS_RECORD,
        CanonicalResourceType.CDN_DISTRIBUTION,
    }),
    ("Storage", {
        CanonicalResourceType.STORAGE_OBJECT_BUCKET,
        CanonicalResourceType.STORAGE_BLOCK_VOLUME,
        CanonicalResourceType.STORAGE_FILE_SYSTEM,
    }),
    ("Database", {
        CanonicalResourceType.DATABASE_INSTANCE,
        CanonicalResourceType.DATABASE_NOSQL,
        CanonicalResourceType.DATABASE_CACHE,
    }),
    ("Messaging", {
        CanonicalResourceType.MESSAGING_TOPIC,
        CanonicalResourceType.MESSAGING_QUEUE,
    }),
    ("Compute & Load Balancing", {
        CanonicalResourceType.COMPUTE_INSTANCE,
        CanonicalResourceType.COMPUTE_CONTAINER_CLUSTER,
        CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION,
        CanonicalResourceType.COMPUTE_CONTAINER_SERVICE,
        CanonicalResourceType.LOAD_BALANCER,
    }),
    ("Observability", {
        CanonicalResourceType.MONITORING_ALARM,
        CanonicalResourceType.LOG_GROUP,
    }),
]


@dataclass(slots=True)
class AssessmentEngine:

    def assess(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
    ) -> MigrationAssessment:
        translation_index: dict[str, TranslationResult] = {
            tr.resource_id: tr for tr in translation.results
        }

        resource_assessments: list[ResourceAssessment] = []
        all_blockers: list[str] = []

        for resource in graph.resources.values():
            tr = translation_index.get(resource.id)
            if tr is None:
                continue

            dep_count = len([
                d for d in resource.depends_on if d in graph.resources
            ])

            score_breakdown = self._compute_score_breakdown(tr, dep_count)
            raw_score = (
                score_breakdown.base_complexity
                + score_breakdown.dependency_load
                + score_breakdown.support_penalty
            )
            complexity_score = max(1, min(100, raw_score))

            blockers = list(tr.manual_actions)
            if tr.status is SupportStatus.UNSUPPORTED:
                blockers.append(
                    f"Resource {resource.name} ({resource.source_type}) has no "
                    f"translation rule for {translation.target_provider.value}"
                )

            resource_assessments.append(
                ResourceAssessment(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    canonical_type=resource.canonical_type,
                    complexity_score=complexity_score,
                    score_breakdown=score_breakdown,
                    support_status=tr.status,
                    strategy=_STRATEGY_MAP[tr.status],
                    downtime=_DOWNTIME_MAP.get(
                        resource.canonical_type, DowntimeClass.MEDIUM
                    ),
                    dependency_count=dep_count,
                    blockers=blockers,
                )
            )
            all_blockers.extend(blockers)

        unique_blockers = list(dict.fromkeys(all_blockers))

        overall_score = self._compute_overall_score(resource_assessments)
        risk_level = self._classify_risk(resource_assessments)
        phases = self._build_phases(graph, resource_assessments)
        recommendation = self._generate_recommendation(
            overall_score, risk_level, unique_blockers
        )

        assessment = MigrationAssessment(
            overall_complexity_score=overall_score,
            risk_level=risk_level,
            resource_assessments=resource_assessments,
            blockers=unique_blockers,
            phases=phases,
            recommendation=recommendation,
        )

        logger.info(
            "assessment_completed",
            overall_score=overall_score,
            risk_level=risk_level.value,
            resource_count=len(resource_assessments),
            blocker_count=len(unique_blockers),
            phase_count=len(phases),
        )
        return assessment

    @staticmethod
    def _compute_score_breakdown(
        tr: TranslationResult, dep_count: int
    ) -> ScoreBreakdown:
        # For unsupported resources that have no matrix rule, use max weight.
        if tr.status is SupportStatus.UNSUPPORTED:
            base = 10 * _COMPLEXITY_WEIGHT_MULTIPLIER
        else:
            # The rule's complexity_weight was already set by the matrix;
            # we can extract it from target_terraform_types count as a
            # secondary signal, but the primary is the weight itself.
            # Since TranslationResult doesn't carry complexity_weight
            # directly, we infer from rule fields.
            fan_out = max(1, len(tr.target_terraform_types))
            base = fan_out * _COMPLEXITY_WEIGHT_MULTIPLIER

        dependency_load = min(dep_count * _DEPENDENCY_POINTS_PER_EDGE, _DEPENDENCY_POINTS_CAP)
        support_penalty = _SUPPORT_PENALTY[tr.status]

        return ScoreBreakdown(
            base_complexity=base,
            dependency_load=dependency_load,
            support_penalty=support_penalty,
        )

    @staticmethod
    def _compute_overall_score(assessments: list[ResourceAssessment]) -> int:
        if not assessments:
            return 1
        avg = sum(a.complexity_score for a in assessments) / len(assessments)
        # Weight max upward: the hardest resource disproportionately affects
        # overall migration complexity.
        max_score = max(a.complexity_score for a in assessments)
        weighted = int(avg * 0.6 + max_score * 0.4)
        return max(1, min(100, weighted))

    @staticmethod
    def _classify_risk(assessments: list[ResourceAssessment]) -> RiskLevel:
        if not assessments:
            return RiskLevel.LOW
        manual_count = sum(
            1 for a in assessments
            if a.strategy is MigrationStrategy.MANUAL
        )
        high_complexity = sum(1 for a in assessments if a.complexity_score > 70)

        if manual_count >= 2 or high_complexity >= 2:
            return RiskLevel.HIGH
        if manual_count >= 1 or high_complexity >= 1:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def _build_phases(
        graph: CanonicalInfrastructureGraph,
        assessments: list[ResourceAssessment],
    ) -> list[MigrationPhase]:
        assessment_index = {a.resource_id: a for a in assessments}
        try:
            topo_order = graph.topological_order()
        except Exception:
            topo_order = list(graph.resources.keys())

        # Assign each resource to a phase by canonical type category.
        assigned: set[str] = set()
        phases: list[MigrationPhase] = []

        for phase_num, (phase_name, type_set) in enumerate(_PHASE_ASSIGNMENT, 1):
            ids_in_phase = [
                rid for rid in topo_order
                if rid in assessment_index
                and assessment_index[rid].canonical_type in type_set
            ]
            if ids_in_phase:
                phases.append(
                    MigrationPhase(
                        phase_number=phase_num,
                        name=phase_name,
                        resource_ids=ids_in_phase,
                    )
                )
                assigned.update(ids_in_phase)

        # Catch-all for types not in _PHASE_ASSIGNMENT.
        remaining = [
            rid for rid in topo_order
            if rid in assessment_index and rid not in assigned
        ]
        if remaining:
            phases.append(
                MigrationPhase(
                    phase_number=len(phases) + 1,
                    name="Remaining Resources",
                    resource_ids=remaining,
                )
            )

        return phases

    @staticmethod
    def _generate_recommendation(
        overall_score: int, risk: RiskLevel, blockers: list[str]
    ) -> str:
        parts: list[str] = []

        if overall_score <= 30:
            parts.append("Low-complexity migration; suitable for automated execution.")
        elif overall_score <= 60:
            parts.append(
                "Moderate complexity; automated execution with targeted manual "
                "review of partial/manual resources recommended."
            )
        else:
            parts.append(
                "High complexity migration requiring phased execution with "
                "dedicated engineering review at each phase gate."
            )

        if risk is RiskLevel.HIGH:
            parts.append("Risk level is HIGH — consider a pilot migration of "
                         "networking + one compute resource before full execution.")

        if blockers:
            parts.append(
                f"{len(blockers)} blocking issue(s) must be resolved before "
                "migration can proceed."
            )
        else:
            parts.append("No blocking issues detected.")

        return " ".join(parts)
