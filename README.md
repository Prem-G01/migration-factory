# Migration Factory — Foundation & Ingestion Layer (Phase 0 + Phase 1)

![CI](https://github.com/Prem-G01/migration-factory/actions/workflows/ci.yml/badge.svg)

AI-Powered Multi-Cloud Infrastructure Migration Factory. This repository
currently implements **Phase 0 (Foundation)** and a working **Phase 1
vertical slice** (Terraform State ingestion, AWS → GCP path): parse
Terraform state → normalize into a provider-agnostic Canonical
Infrastructure Model → validate the dependency graph.

## Why a phased repo instead of all modules at once

A platform of this scope (25+ engines: security, FinOps, compliance, AI
reasoning, Terraform generation, deployment, drift detection, reporting...)
cannot be *built* — reviewed, tested, trusted in production — in a single
pass. Each phase below is a real, installable, tested package increment.
Building "everything" as unreviewed scaffolding would produce exactly the
demo-level code this platform exists to avoid.

## Pipeline (this repo implements the first three stages)

```
 Input (.tfstate)
       │
       ▼
 ┌─────────────┐   ParsedResource       ┌─────────────┐   CanonicalResource   ┌───────────────────────────┐
 │   Parser    │ ─────────────────────▶ │   Mapper    │ ─────────────────────▶│ CanonicalInfrastructureGraph │
 │ (provider-  │   (provider-native,    │(Normalizer) │  (provider-agnostic,  │  + topological_order()     │
 │  native IO) │    pre-normalization)  │             │   shared vocabulary)  │  + validate_references()   │
 └─────────────┘                        └─────────────┘                       └───────────────────────────┘
```

Every future engine (Dependency, AI, Security, FinOps, Compliance, Terraform
Generator, ...) reads from `CanonicalInfrastructureGraph` exclusively — never
from raw input. That single invariant is what keeps N input formats and M
target-cloud generators an `N + M` problem instead of `N × M`.

## Module map (this repo)

| Module | Responsibility |
|---|---|
| `core/config.py` | Env-driven, validated, nested settings — the only place that reads env vars |
| `core/logging.py` | Structured JSON logs with `trace_id`/`execution_id` propagated via contextvars |
| `core/exceptions.py` | Exception hierarchy: every error carries `error_code`, `context`, `remediation` |
| `core/plugin_manager.py` | Generic entry-point-based plugin loader (parsers/mappers register here) |
| `core/container.py` | Explicit, minimal DI container (composition root pattern) |
| `domain/canonical_model.py` | The Canonical Infrastructure Model + dependency graph (topo sort, cycle detection) |
| `parsers/terraform_state.py` | Terraform state (format v4) → `ParsedResource[]` |
| `mappers/aws_to_canonical.py` | AWS-native `ParsedResource` → `CanonicalResource` |
| `pipeline.py` | Composition root: wires Parser Registry → Mapper Registry → Graph |
| `cli.py` | `migration-factory ingest <file>` |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the full test suite (unit + integration + coverage)
pytest

# Lint + type-check (both required to pass CI)
ruff check .
mypy src

# Run the CLI against the bundled sample estate
migration-factory ingest tests/fixtures/sample_terraform.tfstate
```

## API

`pip install -e ".[api]"` then `uvicorn migration_factory.api.main:app --reload --port 8000`.
Interactive docs are auto-generated at `/docs` (Swagger UI) and `/redoc`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/v1/health | GET | Health check |
| /api/v1/analyze | POST | Upload + analyze infrastructure |
| /api/v1/report/{id} | GET | Full JSON report |
| /api/v1/report/{id}/html | GET | HTML report |
| /api/v1/terraform/{id} | GET | Download Terraform zip |
| /api/v1/runs | GET | List all runs |

## Extending: adding a new parser or mapper

No core code changes required — register an entry point:

```toml
[project.entry-points."migration_factory.parsers"]
cloudformation = "migration_factory.parsers.cloudformation:CloudFormationParser"
```

Implement `BaseParser` (`parsers/base.py`) or `BaseMapper` (`mappers/base.py`)
and the Plugin Manager discovers it automatically at startup — this is the
"zero hardcoding / plugin based" requirement in practice, not just in name.

## Roadmap

- **Phase 2** — Dependency Engine (cross-resource graph analysis beyond
  topo-sort: circular-dependency remediation suggestions, blast-radius
  analysis), AI Engine (migration plan generation, root-cause analysis)
- **Phase 3** — Security Engine (CIS benchmark, least-privilege analysis),
  FinOps Engine (cost estimation, rightsizing), Compliance/Policy Engine
- **Phase 4** — Terraform Generator (GCP target), Validation Engine,
  Deployment/Rollback Engine
- **Phase 5** — Drift Detection, Audit Engine, Reporting, Documentation
  Engine

## Design decisions worth knowing before extending this code

- **DI container is intentionally minimal** (no `dependency-injector`/reflection
  magic) — see docstring in `core/container.py` for the tradeoff.
- **Canonical resource IDs** are `f"{provider}:{terraform_address}"` — see
  docstring in `mappers/aws_to_canonical.py`. This is a real constraint on
  future mappers: cross-state dependency resolution is explicitly deferred
  to the Phase 2 Dependency Engine, not solved ad hoc per-mapper.
- **Unsupported resource types do not abort a run** by default
  (`parsing.fail_on_unsupported_resource=False`) — real-world estates are
  messy; partial ingestion with a clear report beats an all-or-nothing
  failure. Flip the setting for strict CI-gated runs.
