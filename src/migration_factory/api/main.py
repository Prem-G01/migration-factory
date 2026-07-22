"""FastAPI REST layer over the Migration Factory pipeline.

Wraps the same engines the CLI (`migration_factory.cli`) drives, but headless
(no Rich console output) and returning JSON instead of a terminal report.
Run results are kept in an in-memory dict keyed by run_id; this is a POC
convenience, not a durable store — restarting the process drops all runs,
and it is not safe to share across multiple worker processes.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import time
import uuid
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.compliance.engine import ComplianceEngine
from migration_factory.core.config import get_settings
from migration_factory.core.exceptions import MigrationFactoryError, ParserError
from migration_factory.discovery.engine import DiscoveryEngine
from migration_factory.domain.enums import CloudProvider
from migration_factory.finops.engine import FinOpsEngine
from migration_factory.knowledge_graph.engine import KnowledgeGraphEngine
from migration_factory.pipeline import IngestionPipeline
from migration_factory.planner.engine import MigrationPlanner
from migration_factory.reporting.engine import ReportingEngine
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_Target = Literal["gcp", "aws", "analyze_only"]

# In-memory run store. POC-grade only: not persisted, not shared across
# worker processes, cleared on restart.
# {run_id: {"report": {...}, "summary": {...}, "direction": str, "mode": str,
#           "terraform_files": list[GeneratedFile] | None, "html": str}}
_RUNS: dict[str, dict[str, Any]] = {}


def _direction_label(source_provider: CloudProvider, target_provider: CloudProvider) -> str:
    return f"{source_provider.value.upper()} → {target_provider.value.upper()}"


def _run_pipeline(source_path: Path, target: _Target | None) -> dict[str, Any]:
    """Ingest -> discover -> translate -> assess -> secure -> comply ->
    cost -> validate -> plan -> (optionally) generate Terraform -> report.
    Mirrors the CLI's `_poc_pipeline` stage order, without Rich rendering.
    A missing/None target means analyze_only: same-cloud analysis, no
    Terraform generated.
    """
    started_at = time.perf_counter()
    settings = get_settings()
    ingestion = IngestionPipeline(settings=settings).run(source_path)

    provider_counts = Counter(r.source_provider.value for r in ingestion.graph.resources.values())
    source_provider = (
        CloudProvider(provider_counts.most_common(1)[0][0]) if provider_counts else CloudProvider.AWS
    )

    if target is None or target == "analyze_only":
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
    terraform_report = None
    if mode == "migrate":
        generator = TerraformGenerator(target_provider=target_provider, project_id="api-run-project")
        terraform_report = generator.generate(ingestion.graph, translation)
        terraform_files = terraform_report.files

    migration_report = ReportingEngine().generate(
        assessment=assessment,
        translation=translation,
        security=security,
        compliance=compliance,
        finops=finops,
        validation=validation,
        terraform=terraform_report,
    )
    html_report = ReportingEngine().to_html(migration_report)

    direction = _direction_label(source_provider, target_provider)
    summary: dict[str, Any] = {
        "resources": len(ingestion.graph.resources),
        "complexity_score": assessment.overall_complexity_score,
        "risk_level": assessment.risk_level.value,
        "confidence_score": plan.confidence.overall_confidence,
        "security_score": security.security_score,
        "compliance_score": compliance.overall_compliance_score,
        "monthly_savings": finops.cost_summary.monthly_savings,
        "downtime_minutes": plan.cutover_plan.total_downtime_minutes,
        "waves": len(plan.waves),
        "blockers": len(assessment.blockers),
    }

    run_id = str(uuid.uuid4())
    duration_seconds = round(time.perf_counter() - started_at, 2)

    full_report: dict[str, Any] = {
        "run_id": run_id,
        "status": "completed",
        "mode": mode,
        "direction": direction,
        "duration_seconds": duration_seconds,
        "source_provider": source_provider.value,
        "target_provider": target_provider.value,
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
        "summary": summary,
    }

    _RUNS[run_id] = {
        "report": full_report,
        "summary": summary,
        "direction": direction,
        "mode": mode,
        "terraform_files": terraform_files,
        "html": html_report,
    }

    return {
        "run_id": run_id,
        "status": "completed",
        "direction": direction,
        "duration_seconds": duration_seconds,
        "summary": summary,
    }


@app.post("/api/v1/analyze")
def analyze(
    file: UploadFile = File(..., description="Terraform state (.tfstate), JSON, or CSV inventory file"),
    target: _Target | None = Form(None, description='One of: "gcp", "aws", "analyze_only" (omit for analyze_only)'),
) -> dict[str, Any]:
    suffix = Path(file.filename or "upload").suffix or ".tfstate"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        return _run_pipeline(tmp_path, target)
    except ParserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MigrationFactoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/v1/report/{run_id}")
def get_report(run_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id!r}")
    result: dict[str, Any] = run["report"]
    return result


@app.get("/api/v1/report/{run_id}/html", response_class=HTMLResponse)
def get_report_html(run_id: str) -> HTMLResponse:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id!r}")
    return HTMLResponse(content=run["html"])


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

    filename = f"migration-terraform-{run_id[:8]}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/v1/runs")
def list_runs() -> dict[str, Any]:
    runs = [
        {"run_id": run_id, "direction": data["direction"], "mode": data["mode"], **data["summary"]}
        for run_id, data in _RUNS.items()
    ]
    return {"runs": runs}


@app.delete("/api/v1/runs/{run_id}")
def delete_run(run_id: str) -> dict[str, bool]:
    if run_id not in _RUNS:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id!r}")
    del _RUNS[run_id]
    return {"deleted": True}


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    # Static build metadata — update alongside the actual test/engine counts.
    return {
        "status": "ok",
        "version": "2.0.3",
        "engines": 28,
        "supported_sources": ["aws", "gcp", "azure"],
        "supported_targets": ["gcp", "aws"],
        "parsers": 10,
        "tests_passing": 346,
    }
