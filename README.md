# Migration Factory

![CI](https://github.com/Prem-G01/migration-factory/actions/workflows/ci.yml/badge.svg)

AI-Powered Multi-Cloud Infrastructure Migration Factory. Parse an existing
AWS or GCP estate (Terraform state, CloudFormation, ARM templates, CMDB
exports, spreadsheets...) into a provider-agnostic Canonical Infrastructure
Model, then assess, secure, cost, plan, and generate real Terraform for the
other cloud — bidirectionally (AWS → GCP and GCP → AWS) — via CLI, REST
API, or the React web dashboard.

## Pipeline

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

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Pipeline engines | Python 3.11+, Pydantic v2, structlog |
| REST API | FastAPI + uvicorn + SQLAlchemy async |
| Database | SQLite (dev) / PostgreSQL (production, via Docker) |
| Web dashboard | React 19 + Vite + Tailwind CSS |
| IaC output | Terraform HCL (GCP + AWS providers) |
| Testing | pytest, 346 tests, ~85% coverage |
| CI | GitHub Actions (ruff, mypy --strict, pytest --cov) |

## Supported Inputs

| Format | Auto-detected by |
|--------|-----------------|
| Terraform state (.tfstate) | `format_version` + `resources` keys |
| Terraform plan (JSON) | `resource_changes` key |
| Terraform HCL (.tf) | File extension |
| CloudFormation | `AWSTemplateFormatVersion` or `Resources` key |
| ARM Template (Azure) | `$schema` (containing "azure") + `resources` key |
| CSV inventory | File extension |
| Excel inventory (.xlsx) | File extension |
| JSON inventory | `inventory` or `resources` key |
| ServiceNow CMDB | `result` or `cmdb_ci` key |
| Terraform log | `Terraform` + plan/apply/refresh keywords |

## Migration Directions

| Case | CLI | REST API |
|---|---|---|
| AWS estate, analyze only | `poc aws.tfstate --mode analyze` | `POST /analyze` (omit `target`, or `target=analyze_only`) |
| GCP estate, analyze only | `poc gcp.tfstate --mode analyze` | same |
| AWS → GCP migration | `poc aws.tfstate --target gcp` | `POST /analyze` with `target=gcp` |
| GCP → AWS migration | `poc gcp.tfstate --target aws` | `POST /analyze` with `target=aws` |

## Quickstart — CLI

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                          # 346 tests
ruff check .                    # lint
mypy src                        # strict type check

migration-factory poc tests/fixtures/sample_terraform.tfstate --target gcp --output ./output
```

## Quickstart — REST API + Dashboard

```bash
# API — SQLite, no external database needed to try it
pip install -e ".[api]"
export MF_DATABASE__URL="sqlite+aiosqlite:///./local.db"   # omit to use Postgres (the coded default)
alembic upgrade head
uvicorn migration_factory.api.main:app --reload --port 8000

# Dashboard, in a second terminal
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173` for the dashboard, `http://localhost:8000/docs`
for interactive Swagger docs.

### Docker (API + Postgres + frontend, one command)

```bash
docker-compose up --build
```

Builds the API image, starts Postgres 16 (Alembic migrations run
automatically on API container start via `docker-entrypoint.sh`), and
serves the built frontend through nginx — `http://localhost` for the
dashboard, `http://localhost:8000` for the API.

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
- The frontend has no automated test suite yet (manual/curl-verified only).
- Live cloud discovery (`discovery/aws_live.py`, `gcp_live.py`,
  `azure_live.py` — reading a real running account rather than a state
  file export) and PDF report rendering are excluded from the coverage
  gate (`pyproject.toml`'s `[tool.coverage.run] omit`): both need live
  cloud credentials or heavy SDK mocking to test honestly.
