"""FastAPI REST layer over the Migration Factory pipeline.

Wraps the same engines the CLI (`migration_factory.cli`) drives, but headless
(no Rich console output) and returning JSON instead of a terminal report.
Run results are kept in an in-memory dict keyed by run_id; this is a POC
convenience, not a durable store — restarting the process drops all runs.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import uuid
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.compliance.engine import ComplianceEngine
from migration_factory.core.config import get_settings
from migration_factory.discovery.engine import DiscoveryEngine
from migration_factory.domain.enums import CloudProvider
from migration_factory.finops.engine import FinOpsEngine
from migration_factory.knowledge_graph.engine import KnowledgeGraphEngine
from migration_factory.pipeline import IngestionPipeline
from migration_factory.planner.engine import MigrationPlanner
from migration_factory.rollback.engine import RollbackPlanner
from migration_factory.security.engine import SecurityEngine
from migration_factory.terraform_gen.engine import GeneratedFile, TerraformGenerator
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
from migration_factory.validation.engine import ValidationEngine

app = FastAPI(
    title="Migration Factory API",
    version="2.0.3",
    description="REST API for the AI-Powered Multi-Cloud Infrastructure Migration Factory",
)

_VALID_TARGETS = {"gcp", "aws", "analyze_only"}

# In-memory run store. POC-grade only: not persisted, not shared across
# worker processes, cleared on restart. {run_id: {"report": ..., "terraform_files": ...}}
_RUNS: dict[str, dict[str, Any]] = {}


def _run_pipeline(source_path: Path, target: str) -> dict[str, Any]:
    """Ingest -> discover -> translate -> assess -> secure -> comply ->
    cost -> validate -> plan -> (optionally) generate Terraform. Mirrors
    the CLI's `_poc_pipeline` stage order, without the Rich rendering.
    """
    settings = get_settings()
    ingestion = IngestionPipeline(settings=settings).run(source_path)

    provider_counts = Counter(r.source_provider.value for r in ingestion.graph.resources.values())
    source_provider = (
        CloudProvider(provider_counts.most_common(1)[0][0]) if provider_counts else CloudProvider.AWS
    )

    if target == "analyze_only":
        target_provider = source_provider
        mode = "analyze"
    else:
        target_provider = CloudProvider.GCP if target == "gcp" else CloudProvider.AWS
        mode = "migrate"

    DiscoveryEngine().enrich(ingestion.graph)
    knowledge_graph = KnowledgeGraphEngine().analyze(ingestion.graph)

    if source_provider is target_provider:
        # No capability matrix exists for a provider mapped to itself
        # (there is no aws_to_aws.json) — same-cloud analysis is an
        # identity translation instead of a matrix lookup.
        translation = TranslationEngine.build_identity_report(ingestion.graph, source_provider)
    else:
        matrix = load_builtin_matrix(source_provider, target_provider)
        translation = TranslationEngine(matrix=matrix).translate(ingestion.graph)

    assessment = AssessmentEngine().assess(ingestion.graph, translation)
    security = SecurityEngine().analyze(ingestion.graph)
    compliance = ComplianceEngine().evaluate(ingestion.graph)
    finops = FinOpsEngine(target_provider=target_provider).analyze(ingestion.graph)
    validation = ValidationEngine().validate(ingestion.graph)
    plan = MigrationPlanner().plan(ingestion.graph, assessment, translation)
    rollback = RollbackPlanner().plan(ingestion.graph, translation)

    terraform_files: list[GeneratedFile] | None = None
    if mode == "migrate":
        generator = TerraformGenerator(target_provider=target_provider, project_id="api-run-project")
        terraform_report = generator.generate(ingestion.graph, translation)
        terraform_files = terraform_report.files

    run_id = str(uuid.uuid4())
    report: dict[str, Any] = {
        "run_id": run_id,
        "mode": mode,
        "source_provider": source_provider.value,
        "target_provider": target_provider.value,
        "resource_count": len(ingestion.graph.resources),
        "unsupported_resources": ingestion.unsupported_resources,
        "knowledge_graph": knowledge_graph,
        "translation_summary": translation.summary,
        "assessment": assessment,
        "security": security,
        "compliance": compliance,
        "finops": finops,
        "validation": validation,
        "plan": plan,
        "rollback": rollback,
        "terraform_available": terraform_files is not None,
    }

    _RUNS[run_id] = {"report": report, "terraform_files": terraform_files}
    return report


@app.post("/api/v1/analyze")
def analyze(
    file: UploadFile = File(..., description="Terraform state (.tfstate), JSON, or CSV inventory file"),
    target: str = Form(..., description='One of: "gcp", "aws", "analyze_only"'),
) -> dict[str, Any]:
    if target not in _VALID_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"target must be one of {sorted(_VALID_TARGETS)}, got {target!r}",
        )

    suffix = Path(file.filename or "upload").suffix or ".tfstate"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        return _run_pipeline(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/v1/report/{run_id}")
def get_report(run_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id!r}")
    result: dict[str, Any] = run["report"]
    return result


@app.get("/api/v1/terraform/{run_id}")
def get_terraform(run_id: str) -> StreamingResponse:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id!r}")

    terraform_files: list[GeneratedFile] | None = run.get("terraform_files")
    if not terraform_files:
        raise HTTPException(
            status_code=404,
            detail=f"No Terraform was generated for run {run_id!r} (analyze_only mode has no Terraform output)",
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for generated_file in terraform_files:
            zf.writestr(generated_file.filename, generated_file.content.encode("utf-8"))
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="terraform-{run_id}.zip"'},
    )


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    # Static build metadata — update alongside the actual test/engine counts.
    return {"status": "ok", "version": "2.0.3", "tests": 334, "engines": 28}
