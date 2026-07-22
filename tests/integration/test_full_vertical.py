"""Full vertical slice integration test: Terraform state file ->
Parse -> Normalize -> Translate (AWS -> GCP) -> Assess.

This test proves the entire data flow works end-to-end against a realistic
fixture, including dependency ordering, translation decisions, assessment
scoring, and phased migration planning. It's the single test that, if green,
gives confidence the platform works as a coherent unit — not just as
isolated modules.
"""

from __future__ import annotations

from pathlib import Path

from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.assessment.models import (
    MigrationStrategy,
)
from migration_factory.core.config import Settings
from migration_factory.domain.enums import CloudProvider
from migration_factory.pipeline import IngestionPipeline
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
from migration_factory.translation.models import SupportStatus


def test_full_vertical_aws_to_gcp(sample_tfstate_path: Path) -> None:
    # Phase 1: Ingest
    pipeline = IngestionPipeline(settings=Settings())
    ingestion = pipeline.run(sample_tfstate_path)

    assert len(ingestion.graph.resources) == 6
    assert ingestion.unsupported_resources == []

    # Phase 2: Translate
    matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
    translation = TranslationEngine(matrix=matrix).translate(ingestion.graph)

    assert len(translation.results) == 6
    assert translation.source_provider is CloudProvider.AWS
    assert translation.target_provider is CloudProvider.GCP

    # Spot-check translation decisions match the matrix
    by_id = {r.resource_id: r for r in translation.results}

    vpc_tr = by_id["aws:aws_vpc.main"]
    assert vpc_tr.status is SupportStatus.SUPPORTED
    assert "google_compute_network" in vpc_tr.target_terraform_types

    sg_tr = by_id["aws:aws_security_group.app"]
    assert sg_tr.status is SupportStatus.PARTIAL

    role_tr = by_id["aws:aws_iam_role.app_role"]
    assert role_tr.status is SupportStatus.MANUAL
    assert len(role_tr.manual_actions) > 0

    # Every result has a non-empty rationale
    for tr in translation.results:
        assert len(tr.rationale) > 10, f"{tr.resource_id}: missing rationale"

    # Phase 3: Assess
    assessment = AssessmentEngine().assess(ingestion.graph, translation)

    assert 1 <= assessment.overall_complexity_score <= 100
    assert len(assessment.resource_assessments) == 6

    # IAM role should be MANUAL strategy
    role_assessment = next(
        a for a in assessment.resource_assessments
        if a.resource_id == "aws:aws_iam_role.app_role"
    )
    assert role_assessment.strategy is MigrationStrategy.MANUAL

    # EC2 instance should be REHOST
    instance_assessment = next(
        a for a in assessment.resource_assessments
        if a.resource_id == "aws:aws_instance.app"
    )
    assert instance_assessment.strategy is MigrationStrategy.REHOST

    # Phases should start with Networking and end with Compute
    phase_names = [p.name for p in assessment.phases]
    assert phase_names[0] == "Networking"
    assert "Compute & Load Balancing" in phase_names

    # Networking phase: VPC before subnet (dependency respected)
    net_phase = assessment.phases[0]
    vpc_idx = net_phase.resource_ids.index("aws:aws_vpc.main")
    subnet_idx = net_phase.resource_ids.index("aws:aws_subnet.app")
    assert vpc_idx < subnet_idx

    # Assessment should flag blockers (IAM manual actions)
    assert len(assessment.blockers) > 0

    # Recommendation should be present and non-trivial
    assert len(assessment.recommendation) > 20
