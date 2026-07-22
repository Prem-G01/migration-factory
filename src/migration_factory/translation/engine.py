"""Translation Engine.

Deterministic: (CanonicalInfrastructureGraph, CapabilityMatrix) ->
TranslationReport. No AI, no network calls, no randomness — the same graph
and matrix always produce the same report. That property is what makes the
output auditable and what lets the AI Advisor (later phase) safely reason
ON TOP of translations instead of being trusted to produce them.
"""

from __future__ import annotations

from dataclasses import dataclass

from migration_factory.core.exceptions import TranslationError
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.domain.enums import CloudProvider
from migration_factory.translation.matrix import CapabilityMatrix
from migration_factory.translation.models import (
    SupportStatus,
    TranslationReport,
    TranslationResult,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class TranslationEngine:
    matrix: CapabilityMatrix

    def translate(self, graph: CanonicalInfrastructureGraph) -> TranslationReport:
        self._validate_graph_provider(graph)

        results: list[TranslationResult] = []
        for resource in graph.resources.values():
            rule = self.matrix.rule_for(resource.canonical_type)

            if rule is None:
                # Explicit, explained fallback — never silently drop. An
                # unmapped type is a first-class UNSUPPORTED decision with its
                # own rationale, and it surfaces as an assessment blocker.
                results.append(
                    TranslationResult(
                        resource_id=resource.id,
                        resource_name=resource.name,
                        canonical_type=resource.canonical_type,
                        status=SupportStatus.UNSUPPORTED,
                        rationale=(
                            f"No translation rule exists in matrix "
                            f"{self.matrix.matrix_version!r} for canonical type "
                            f"{resource.canonical_type.value!r} targeting "
                            f"{self.matrix.target_provider.value}. This resource "
                            "requires either a matrix extension or a manual "
                            "migration decision."
                        ),
                    )
                )
                logger.warning(
                    "translation_unsupported",
                    resource_id=resource.id,
                    canonical_type=resource.canonical_type.value,
                )
                continue

            results.append(
                TranslationResult(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    canonical_type=resource.canonical_type,
                    status=rule.status,
                    target_service=rule.target_service,
                    target_terraform_types=list(rule.target_terraform_types),
                    required_changes=list(rule.required_changes),
                    manual_actions=list(rule.manual_actions),
                    rationale=rule.rationale,
                )
            )

        report = TranslationReport(
            source_provider=self.matrix.source_provider,
            target_provider=self.matrix.target_provider,
            results=results,
        )
        logger.info(
            "translation_completed",
            resource_count=len(results),
            **{f"status_{k}": v for k, v in report.summary.items()},
        )
        return report

    @staticmethod
    def build_identity_report(
        graph: CanonicalInfrastructureGraph, provider: CloudProvider
    ) -> TranslationReport:
        """Same-cloud analysis report: no cross-cloud translation is happening
        (source and target provider are identical), so every resource is
        trivially SUPPORTED as-is. Used for single-cloud "analyze only" runs,
        which have no capability matrix to load (there is no aws_to_aws.json —
        an identity mapping is code, not curated migration data).
        """
        results = [
            TranslationResult(
                resource_id=resource.id,
                resource_name=resource.name,
                canonical_type=resource.canonical_type,
                status=SupportStatus.SUPPORTED,
                target_service=resource.source_type,
                target_terraform_types=[resource.source_type],
                rationale=(
                    f"Single-cloud analysis: resource already runs natively on "
                    f"{provider.value}; no cross-cloud translation is being performed."
                ),
            )
            for resource in graph.resources.values()
        ]
        return TranslationReport(
            source_provider=provider,
            target_provider=provider,
            results=results,
        )

    def _validate_graph_provider(self, graph: CanonicalInfrastructureGraph) -> None:
        """A translation run is defined for exactly one source provider.
        Mixed-provider graphs (valid for discovery/inventory) must be split
        by the caller before translation — silently translating half a graph
        with the wrong matrix would be a correctness disaster.
        """
        providers: set[CloudProvider] = {
            r.source_provider for r in graph.resources.values()
        }
        if not providers:
            return
        if providers != {self.matrix.source_provider}:
            raise TranslationError(
                "Graph provider(s) do not match the capability matrix source provider",
                context={
                    "graph_providers": sorted(p.value for p in providers),
                    "matrix_source_provider": self.matrix.source_provider.value,
                },
                remediation="Split the graph by source provider and translate each "
                "partition with its matching matrix.",
            )
