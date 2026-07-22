"""Bidirectional AWS<->GCP support: the four use cases the platform must
handle without manual intervention — AWS-only analysis, GCP-only analysis,
AWS -> GCP migration, and GCP -> AWS migration.
"""

from __future__ import annotations

from pathlib import Path

from migration_factory.compliance.engine import ComplianceEngine
from migration_factory.core.config import Settings
from migration_factory.domain.enums import CloudProvider
from migration_factory.finops.engine import FinOpsEngine
from migration_factory.pipeline import IngestionPipeline
from migration_factory.security.engine import SecurityEngine
from migration_factory.terraform_gen.engine import TerraformGenerator
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix


def test_aws_only_analysis(sample_tfstate_path: Path) -> None:
    """Case 1: AWS estate analyzed on its own — no migration target,
    no translation, no Terraform generation."""
    pipeline = IngestionPipeline(settings=Settings())
    ingestion = pipeline.run(sample_tfstate_path)

    providers = {r.source_provider for r in ingestion.graph.resources.values()}
    assert providers == {CloudProvider.AWS}

    security = SecurityEngine().analyze(ingestion.graph)
    compliance = ComplianceEngine().evaluate(ingestion.graph)
    finops = FinOpsEngine(target_provider=CloudProvider.AWS).analyze(ingestion.graph)

    assert security.security_score > 0
    assert compliance.overall_compliance_score >= 0
    assert finops.cost_summary.source_monthly_total >= 0


def test_gcp_only_analysis(sample_gcp_tfstate_path: Path) -> None:
    """Case 2: GCP estate analyzed on its own — no migration target."""
    pipeline = IngestionPipeline(settings=Settings())
    ingestion = pipeline.run(sample_gcp_tfstate_path)

    providers = {r.source_provider for r in ingestion.graph.resources.values()}
    assert providers == {CloudProvider.GCP}

    security = SecurityEngine().analyze(ingestion.graph)
    compliance = ComplianceEngine().evaluate(ingestion.graph)
    finops = FinOpsEngine(target_provider=CloudProvider.GCP).analyze(ingestion.graph)

    assert security.security_score >= 0
    assert compliance.overall_compliance_score >= 0
    assert finops.cost_summary.source_monthly_total >= 0


def test_aws_to_gcp_migration(sample_tfstate_path: Path) -> None:
    """Case 3: AWS -> GCP full migration, Terraform generated."""
    pipeline = IngestionPipeline(settings=Settings())
    ingestion = pipeline.run(sample_tfstate_path)

    matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
    translation = TranslationEngine(matrix=matrix).translate(ingestion.graph)
    assert translation.summary["supported"] > 0

    gen = TerraformGenerator(target_provider=CloudProvider.GCP, project_id="test-project")
    report = gen.generate(ingestion.graph, translation)
    assert report.generated_resources > 0

    main_tf = next(f for f in report.files if f.filename == "main.tf")
    assert "google_" in main_tf.content


def test_gcp_to_aws_migration(sample_gcp_tfstate_path: Path) -> None:
    """Case 4: GCP -> AWS full migration, Terraform generated."""
    pipeline = IngestionPipeline(settings=Settings())
    ingestion = pipeline.run(sample_gcp_tfstate_path)

    matrix = load_builtin_matrix(CloudProvider.GCP, CloudProvider.AWS)
    translation = TranslationEngine(matrix=matrix).translate(ingestion.graph)
    assert translation.summary["supported"] > 0

    gen = TerraformGenerator(target_provider=CloudProvider.AWS)
    report = gen.generate(ingestion.graph, translation)
    assert report.generated_resources > 0

    main_tf = next(f for f in report.files if f.filename == "main.tf")
    assert "aws_" in main_tf.content


def test_direction_auto_detection(
    sample_tfstate_path: Path, sample_gcp_tfstate_path: Path
) -> None:
    """Case 5: source provider is detected correctly from each fixture."""
    pipeline = IngestionPipeline(settings=Settings())

    gcp_ingestion = pipeline.run(sample_gcp_tfstate_path)
    gcp_providers = {r.source_provider for r in gcp_ingestion.graph.resources.values()}
    assert gcp_providers == {CloudProvider.GCP}

    aws_ingestion = pipeline.run(sample_tfstate_path)
    aws_providers = {r.source_provider for r in aws_ingestion.graph.resources.values()}
    assert aws_providers == {CloudProvider.AWS}


def test_aws_generator_produces_valid_hcl(sample_gcp_tfstate_path: Path) -> None:
    """Case 6: the AWS Terraform generator emits recognizable AWS HCL,
    including provider configuration."""
    pipeline = IngestionPipeline(settings=Settings())
    ingestion = pipeline.run(sample_gcp_tfstate_path)

    matrix = load_builtin_matrix(CloudProvider.GCP, CloudProvider.AWS)
    translation = TranslationEngine(matrix=matrix).translate(ingestion.graph)

    gen = TerraformGenerator(target_provider=CloudProvider.AWS)
    report = gen.generate(ingestion.graph, translation)

    main_tf = next(f for f in report.files if f.filename == "main.tf")
    providers_tf = next(f for f in report.files if f.filename == "providers.tf")

    assert "aws_vpc" in main_tf.content
    assert "aws_instance" in main_tf.content
    assert "hashicorp/aws" in providers_tf.content
