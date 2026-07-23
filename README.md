# 🏭 Migration Factory

**AI-Powered Multi-Cloud Infrastructure Migration Platform**

![CI](https://github.com/Prem-G01/migration-factory/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Tests](https://img.shields.io/badge/tests-346%20passing-green)
![License](https://img.shields.io/badge/license-MIT-blue)

> Analyze and migrate cloud infrastructure between AWS and GCP in seconds.
> Upload a Terraform state file, get a complete migration plan with
> generated Terraform, security analysis, compliance reports, and a cost
> savings estimate.

## Live Demo

| Step | What happens |
|------|-------------|
| Upload `.tfstate` file | Auto-detected: AWS, GCP, or Azure |
| Select target cloud | GCP, AWS, or Analyze Only |
| Click Analyze | 12-stage pipeline runs (sub-second on the bundled sample fixtures) |
| View results | Complexity score, risk, security, compliance, FinOps |
| Download output | Ready-to-apply Terraform + HTML report |

## 4 Use Cases

| Use Case | Command / Action |
|----------|-----------------|
| AWS → GCP | Upload `.tfstate`, select GCP target |
| GCP → AWS | Upload GCP state, select AWS target |
| AWS Analysis | Upload `.tfstate`, select Analyze Only |
| GCP Analysis | Upload GCP state, select Analyze Only |

## Quick Start (CLI)

```bash
pip install -e .
migration-factory poc tests/fixtures/sample_terraform.tfstate --target gcp --output ./output
```

## Quick Start (Web UI)

```bash
# Terminal 1 — API (the "api" extra pulls in fastapi/uvicorn/sqlalchemy/alembic)
pip install -e ".[api]"
export MF_DATABASE__URL="sqlite+aiosqlite:///./local.db"   # omit to use Postgres (the coded default)
alembic upgrade head
uvicorn migration_factory.api.main:app --port 8000

# Terminal 2 — Dashboard
cd frontend && npm install && npm run dev

# Open browser
http://localhost:5173
```

## Quick Start (API)

```bash
# Analyze AWS infrastructure -> GCP migration plan
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "file=@terraform.tfstate" \
  -F "target=gcp"

# Fetch the full JSON report
curl http://localhost:8000/api/v1/report/{run_id}

# Download generated Terraform
curl http://localhost:8000/api/v1/terraform/{run_id} --output terraform.zip

# Swagger UI
http://localhost:8000/docs
```

### Docker (API + Postgres + frontend, one command)

```bash
docker-compose up --build
```

Builds the API image, starts Postgres 16 (Alembic migrations run
automatically on API container start via `docker-entrypoint.sh`), and
serves the built frontend through nginx — `http://localhost` for the
dashboard, `http://localhost:8000` for the API. See [Known gaps](#known-gaps):
this path is written and code-reviewed but not yet run end-to-end on a
working Docker daemon.

## What You Get

From a `.tfstate` file the platform produces:

- **Executive summary** — complexity score, risk level, confidence, recommendation
- **Translation plan** — which resources migrate cleanly vs need manual work
- **Migration waves** — ordered deployment plan with parallel/sequential optimization
- **Security analysis** — IAM, firewall, and secret-detection findings (score 0–100)
- **Compliance report** — CIS, NIST, SOC2, PCI-DSS, ISO27001, HIPAA (6 frameworks scored)
- **FinOps analysis** — current vs target cost, monthly savings, break-even
- **7 Terraform files** — `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`, `versions.tf`, `backend.tf`, `terraform.tfvars`
- **HTML + Markdown reports** — shareable with stakeholders
- **Mermaid dependency diagram** — CLI-only for now (`--output` writes `dependency-graph.mmd`); not yet surfaced through the API/dashboard

## Architecture

```
 Input file
       │
       ▼
 ┌─────────────┐   ParsedResource       ┌─────────────┐   CanonicalResource   ┌───────────────────────────────┐
 │   Parser    │ ─────────────────────▶ │   Mapper    │ ─────────────────────▶│ CanonicalInfrastructureGraph   │
 │ (provider-  │   (provider-native,    │(Normalizer) │  (provider-agnostic,  │  + topological_order()         │
 │  native IO) │    pre-normalization)  │             │   shared vocabulary)  │  + validate_references()       │
 └─────────────┘                        └─────────────┘                       └───────────────┬───────────────┘
                                                                                                │
                     ┌─────────────┬─────────────┬─────────────┬──────────────┬────────────────┤
                     ▼             ▼             ▼             ▼              ▼                ▼
                Assessment    Security      Compliance      FinOps      Validation    Translation + Terraform Gen
```

Every downstream engine reads from `CanonicalInfrastructureGraph`
exclusively — never from raw input. That single invariant is what keeps N
input formats and M target-cloud generators an `N + M` problem instead of
`N × M`.

The 12 stages a single analysis run drives, in order: ingestion (parse) →
discovery enrichment → knowledge-graph analysis → translation → assessment
→ security → compliance → FinOps → validation → migration planning →
rollback planning → reporting (JSON + HTML). Terraform generation is a
13th stage that only runs in migrate mode (skipped for analyze-only runs).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Pipeline engines | Python 3.11+, Pydantic v2, structlog |
| REST API | FastAPI + uvicorn + SQLAlchemy async |
| Database | SQLite (dev) / PostgreSQL (production) |
| Web dashboard | React 19 + Vite + Tailwind CSS |
| IaC output | Terraform HCL (GCP + AWS providers) |
| Testing | pytest, 346 tests, 85% coverage |
| CI | GitHub Actions |

## Supported Inputs

| Format | Auto-detected by |
|--------|-----------------|
| Terraform state (.tfstate) | `format_version` + `resources` keys |
| Terraform plan (JSON) | `resource_changes` key |
| Terraform HCL (.tf) | File extension |
| CloudFormation | `AWSTemplateFormatVersion` key |
| ARM Template (Azure) (parser available, Azure use cases not in current release scope) | `$schema` + azure URL |
| CSV inventory | File extension |
| Excel inventory (.xlsx) | File extension |
| JSON inventory | `inventory` or `resources` key |
| ServiceNow CMDB | `result` or `cmdb_ci` key |
| Terraform log | `Terraform` + `Apply` keywords |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|--------------|
| GET | /api/v1/health | Health check |
| POST | /api/v1/analyze | Upload file + run full pipeline |
| GET | /api/v1/report/{id} | Full JSON report |
| GET | /api/v1/report/{id}/html | HTML report (open in browser) |
| GET | /api/v1/terraform/{id} | Download Terraform zip |
| GET | /api/v1/runs | List all analysis runs |
| DELETE | /api/v1/runs/{id} | Delete a run |

## Running Tests

```bash
pip install -e ".[dev]"
pytest                          # 346 tests
pytest -v -k "test_api"         # API tests only
pytest --cov --cov-report=html  # coverage report
```

API tests run against an in-memory SQLite database (see
`tests/unit/test_api.py`), not Postgres — the whole suite stays hermetic,
no external service required, same as every other test in this repo.

## Project Structure

```
migration-factory/
├── src/migration_factory/
│   ├── api/              # FastAPI app, SQLAlchemy models, Alembic-managed DB
│   ├── parsers/          # Input format -> ParsedResource (one file per format family)
│   ├── mappers/          # ParsedResource -> CanonicalResource (AWS / GCP / Azure)
│   ├── domain/            # Canonical Infrastructure Model + dependency graph
│   ├── translation/      # Capability matrices (aws_to_gcp.json / gcp_to_aws.json)
│   ├── assessment/       # Complexity scoring, migration strategy, phasing
│   ├── security/         # IAM / secret / firewall findings, security scoring
│   ├── compliance/       # CIS / NIST / SOC2 / PCI-DSS / ISO27001 / HIPAA checks
│   ├── finops/            # Cost estimation, savings, break-even
│   ├── planner/           # Migration waves, cutover plan, confidence score
│   ├── terraform_gen/    # Canonical graph -> real Terraform HCL (GCP + AWS)
│   ├── reporting/         # Markdown / HTML report rendering
│   ├── validation/        # Post-translation sanity checks
│   ├── rollback/          # Rollback plan generation
│   ├── core/               # Config, logging, exceptions, plugin manager
│   └── cli.py              # `migration-factory` entrypoint
├── alembic/                 # Database migrations (async, SQLAlchemy 2.0)
├── frontend/                # React 19 + Vite + Tailwind dashboard
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/            # Sample .tfstate files (AWS + GCP)
├── .github/workflows/       # CI: ruff, mypy --strict, pytest --cov
├── Dockerfile                # API image (multi-stage, auto-runs migrations on start)
├── docker-compose.yml        # api + db (postgres) + frontend
└── pyproject.toml
```

## Extending: adding a new parser or mapper

No core code changes required — register an entry point:

```toml
[project.entry-points."migration_factory.parsers"]
cloudformation = "migration_factory.parsers.cloudformation:CloudFormationParser"
```

Implement `BaseParser` (`parsers/base.py`) or `BaseMapper` (`mappers/base.py`)
and the Plugin Manager discovers it automatically at startup — this is the
"zero hardcoding / plugin based" requirement in practice, not just in name.

## Design decisions worth knowing before extending this code

- **DI container is intentionally minimal** (no `dependency-injector`/reflection
  magic) — see docstring in `core/container.py` for the tradeoff.
- **Canonical resource IDs** are `f"{provider}:{terraform_address}"` — see
  docstring in `mappers/aws_to_canonical.py`. Cross-state dependency
  resolution is a graph-level concern, not solved ad hoc per-mapper.
- **Unsupported resource types do not abort a run** by default
  (`parsing.fail_on_unsupported_resource=False`) — real-world estates are
  messy; partial ingestion with a clear report beats an all-or-nothing
  failure. Flip the setting for strict CI-gated runs.
- **Same-cloud analysis has no capability matrix** (there is no
  `aws_to_aws.json`) — analyzing an estate without migrating it uses an
  identity translation (`TranslationEngine.build_identity_report`) instead
  of a matrix lookup.
- **The API's run store is append-heavy, not multi-tenant**: `MigrationRun`
  rows have no owner/auth concept yet — every run is visible to every API
  caller. Fine for a single-team internal tool, not for a public deployment
  as-is.

## Known gaps

- `docker-compose up --build` (the full API + Postgres + frontend stack) is
  written and reviewed but not yet verified end-to-end on a real Docker
  daemon — the last dev environment it was built on had Docker Desktop
  blocked on a missing WSL2 install. The API has been verified against a
  real database (SQLite, with the actual Alembic migration applied,
  including a full process-restart persistence check).
- The Mermaid dependency diagram (`assessment/extended.py`) is wired into
  the CLI's `--output` directory only — the API/dashboard don't expose it yet.
- The frontend has no automated test suite yet (manual/curl-verified only).
- Live cloud discovery (`discovery/aws_live.py`, `gcp_live.py`,
  `azure_live.py` — reading a real running account rather than a state
  file export) and PDF report rendering are excluded from the coverage
  gate (`pyproject.toml`'s `[tool.coverage.run] omit`): both need live
  cloud credentials or heavy SDK mocking to test honestly.

## License

MIT — see [LICENSE](LICENSE).
