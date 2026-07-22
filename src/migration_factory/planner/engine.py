"""Migration Planner — enhanced planning capabilities.

Extends the basic phase-based planning in the Assessment Engine with:
wave planning, parallel migration optimization, cutover planning,
validation checkpoints, post-migration verification, maintenance window
estimation, and migration confidence scoring.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.assessment.models import MigrationAssessment, MigrationStrategy, ResourceAssessment
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.domain.enums import CanonicalResourceType
from migration_factory.translation.models import SupportStatus, TranslationReport

logger = get_logger(__name__)


class MigrationWave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wave_number: int
    name: str
    resource_ids: list[str] = Field(default_factory=list)
    can_parallelize: bool = False
    estimated_duration_hours: float = 0
    validation_checkpoints: list[str] = Field(default_factory=list)
    rollback_trigger: str = ""


class CutoverStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_number: int
    action: str
    description: str
    estimated_minutes: int
    requires_downtime: bool = False
    validation: str = ""


class CutoverPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_downtime_minutes: int
    steps: list[CutoverStep] = Field(default_factory=list)
    pre_cutover_checks: list[str] = Field(default_factory=list)
    post_cutover_checks: list[str] = Field(default_factory=list)


class MaintenanceWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommended_window_hours: float
    minimum_window_hours: float
    buffer_percentage: float = 30.0
    justification: str = ""


class ConfidenceScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_confidence: int = Field(..., ge=0, le=100, description="Higher = more confident migration will succeed")
    factors: dict[str, int] = Field(default_factory=dict)
    risks_to_confidence: list[str] = Field(default_factory=list)
    confidence_boosters: list[str] = Field(default_factory=list)


class EnhancedMigrationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waves: list[MigrationWave] = Field(default_factory=list)
    cutover_plan: CutoverPlan
    maintenance_window: MaintenanceWindow
    confidence: ConfidenceScore
    post_migration_verification: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class MigrationPlanner:
    """Enhanced migration planner with wave optimization and cutover planning."""

    def plan(
        self,
        graph: CanonicalInfrastructureGraph,
        assessment: MigrationAssessment,
        translation: TranslationReport,
    ) -> EnhancedMigrationPlan:
        waves = self._build_waves(graph, assessment)
        cutover = self._build_cutover_plan(graph, assessment)
        window = self._estimate_maintenance_window(waves, cutover)
        confidence = self._compute_confidence(assessment, translation)
        verification = self._post_migration_verification(graph, translation)

        plan = EnhancedMigrationPlan(
            waves=waves,
            cutover_plan=cutover,
            maintenance_window=window,
            confidence=confidence,
            post_migration_verification=verification,
        )

        logger.info(
            "enhanced_migration_plan_generated",
            wave_count=len(waves),
            confidence=confidence.overall_confidence,
            downtime_minutes=cutover.total_downtime_minutes,
        )
        return plan

    def _build_waves(
        self, graph: CanonicalInfrastructureGraph, assessment: MigrationAssessment
    ) -> list[MigrationWave]:
        """Group phases into waves. Resources with no inter-wave dependencies can parallelize."""
        waves: list[MigrationWave] = []
        assessment_index = {a.resource_id: a for a in assessment.resource_assessments}

        for phase in assessment.phases:
            # Split phase into parallelizable groups
            independent: list[str] = []
            dependent: list[str] = []

            for rid in phase.resource_ids:
                resource = graph.resources.get(rid)
                if resource is None:
                    continue
                # A resource is parallelizable within a wave if its dependencies are all in prior phases
                deps_in_phase = [d for d in resource.depends_on if d in phase.resource_ids]
                if deps_in_phase:
                    dependent.append(rid)
                else:
                    independent.append(rid)

            # Independent resources form a parallel wave
            if independent:
                duration = sum(
                    self._estimate_resource_hours(assessment_index.get(rid))
                    for rid in independent
                )
                waves.append(MigrationWave(
                    wave_number=len(waves) + 1,
                    name=f"{phase.name} (parallel)",
                    resource_ids=independent,
                    can_parallelize=True,
                    estimated_duration_hours=max(
                        self._estimate_resource_hours(assessment_index.get(rid))
                        for rid in independent
                    ),
                    validation_checkpoints=[
                        f"Verify all {phase.name} resources are healthy",
                        f"Run connectivity tests for {phase.name} tier",
                        "Confirm monitoring/alerting is active",
                    ],
                    rollback_trigger=f"Any {phase.name} resource fails health check within 15 minutes",
                ))

            # Dependent resources form a sequential wave
            if dependent:
                duration = sum(
                    self._estimate_resource_hours(assessment_index.get(rid))
                    for rid in dependent
                )
                waves.append(MigrationWave(
                    wave_number=len(waves) + 1,
                    name=f"{phase.name} (sequential)",
                    resource_ids=dependent,
                    can_parallelize=False,
                    estimated_duration_hours=duration,
                    validation_checkpoints=[
                        f"Verify each {phase.name} dependent resource individually",
                        "Confirm dependency chain is intact",
                    ],
                    rollback_trigger=f"Dependency chain broken in {phase.name}",
                ))

        return waves

    def _build_cutover_plan(
        self, graph: CanonicalInfrastructureGraph, assessment: MigrationAssessment
    ) -> CutoverPlan:
        steps: list[CutoverStep] = []
        total_downtime = 0

        steps.append(CutoverStep(
            step_number=1, action="freeze_changes",
            description="Freeze all infrastructure changes on source cloud",
            estimated_minutes=5, requires_downtime=False,
            validation="Confirm no pending deployments or auto-scaling events",
        ))

        # Data sync for stateful resources
        stateful = [
            a for a in assessment.resource_assessments
            if a.canonical_type in {
                CanonicalResourceType.DATABASE_INSTANCE,
                CanonicalResourceType.DATABASE_NOSQL,
                CanonicalResourceType.DATABASE_CACHE,
                CanonicalResourceType.STORAGE_FILE_SYSTEM,
            }
        ]
        if stateful:
            steps.append(CutoverStep(
                step_number=len(steps) + 1, action="final_data_sync",
                description=f"Final data synchronization for {len(stateful)} stateful resources",
                estimated_minutes=max(15, len(stateful) * 10),
                requires_downtime=True,
                validation="Verify data consistency checksums match source and target",
            ))
            total_downtime += max(15, len(stateful) * 10)

        steps.append(CutoverStep(
            step_number=len(steps) + 1, action="dns_switch",
            description="Switch DNS records to point to target infrastructure",
            estimated_minutes=5, requires_downtime=True,
            validation="Verify DNS resolution returns target IPs",
        ))
        total_downtime += 5

        steps.append(CutoverStep(
            step_number=len(steps) + 1, action="traffic_validation",
            description="Validate traffic is flowing through target infrastructure",
            estimated_minutes=10, requires_downtime=False,
            validation="Confirm 200 OK on health endpoints, check error rates",
        ))

        steps.append(CutoverStep(
            step_number=len(steps) + 1, action="monitoring_validation",
            description="Verify all monitoring and alerting is active on target",
            estimated_minutes=5, requires_downtime=False,
            validation="Confirm dashboards show data, test alert firing",
        ))

        return CutoverPlan(
            total_downtime_minutes=total_downtime,
            steps=steps,
            pre_cutover_checks=[
                "All migration waves completed successfully",
                "Target infrastructure passes all validation checks",
                "Rollback plan reviewed and approved",
                "Stakeholders notified of cutover window",
                "On-call team briefed and standing by",
            ],
            post_cutover_checks=[
                "Application health checks passing for 30+ minutes",
                "Error rates below baseline threshold",
                "All critical business transactions verified",
                "Source infrastructure placed in read-only / standby mode",
                "Cutover completion communicated to stakeholders",
            ],
        )

    @staticmethod
    def _estimate_maintenance_window(
        waves: list[MigrationWave], cutover: CutoverPlan
    ) -> MaintenanceWindow:
        total_hours = sum(w.estimated_duration_hours for w in waves)
        cutover_hours = cutover.total_downtime_minutes / 60.0
        minimum = total_hours + cutover_hours
        buffer = 1.3  # 30% buffer
        recommended = minimum * buffer

        return MaintenanceWindow(
            recommended_window_hours=round(recommended, 1),
            minimum_window_hours=round(minimum, 1),
            buffer_percentage=30.0,
            justification=f"{len(waves)} waves, {cutover.total_downtime_minutes}min downtime, "
            f"30% buffer for unexpected issues",
        )

    @staticmethod
    def _compute_confidence(
        assessment: MigrationAssessment, translation: TranslationReport
    ) -> ConfidenceScore:
        factors: dict[str, int] = {}
        risks: list[str] = []
        boosters: list[str] = []

        # Factor: translation coverage
        supported = sum(1 for tr in translation.results if tr.status is SupportStatus.SUPPORTED)
        total = len(translation.results) or 1
        coverage_pct = int(supported / total * 100)
        factors["translation_coverage"] = coverage_pct
        if coverage_pct < 50:
            risks.append(f"Only {coverage_pct}% of resources have full translation support")
        elif coverage_pct > 80:
            boosters.append(f"{coverage_pct}% of resources have clean 1:1 translations")

        # Factor: blocker count
        blocker_penalty = min(50, len(assessment.blockers) * 10)
        factors["blocker_impact"] = 100 - blocker_penalty
        if assessment.blockers:
            risks.append(f"{len(assessment.blockers)} blocking issues must be resolved")
        else:
            boosters.append("No blocking issues detected")

        # Factor: complexity score (inverse — lower complexity = higher confidence)
        complexity_factor = max(0, 100 - assessment.overall_complexity_score)
        factors["complexity_factor"] = complexity_factor

        # Factor: manual resources
        manual_count = sum(1 for a in assessment.resource_assessments if a.strategy is MigrationStrategy.MANUAL)
        manual_penalty = min(40, manual_count * 15)
        factors["automation_level"] = 100 - manual_penalty
        if manual_count > 0:
            risks.append(f"{manual_count} resources require manual migration")

        # Overall: weighted average
        weights = {"translation_coverage": 0.3, "blocker_impact": 0.25, "complexity_factor": 0.25, "automation_level": 0.2}
        overall = int(sum(factors.get(k, 50) * w for k, w in weights.items()))
        overall = max(0, min(100, overall))

        return ConfidenceScore(
            overall_confidence=overall,
            factors=factors,
            risks_to_confidence=risks,
            confidence_boosters=boosters,
        )

    @staticmethod
    def _post_migration_verification(
        graph: CanonicalInfrastructureGraph, translation: TranslationReport
    ) -> list[str]:
        checks = [
            "Run terraform plan on target — expect no changes (drift-free)",
            "Verify all DNS records resolve to target infrastructure",
            "Confirm application health checks are green for 1 hour",
            "Validate monitoring dashboards show expected metrics",
            "Run smoke tests against all critical API endpoints",
            "Verify database connectivity and query performance",
            "Check SSL/TLS certificates are valid and auto-renewing",
            "Confirm log aggregation is capturing from all target resources",
            "Validate IAM permissions allow expected operations",
            "Run security scan against target infrastructure",
            "Compare source and target cost reports for first billing cycle",
            "Decommission source infrastructure after soak period (7-30 days)",
        ]
        return checks

    @staticmethod
    def _estimate_resource_hours(assessment: ResourceAssessment | None) -> float:
        if assessment is None:
            return 1.0
        if assessment.strategy is MigrationStrategy.MANUAL:
            return 4.0
        if assessment.strategy is MigrationStrategy.REPLATFORM:
            return 2.0
        return 0.5
