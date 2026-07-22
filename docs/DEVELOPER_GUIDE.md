# Developer Guide

## Architecture overview

The platform follows a strict pipeline architecture where every input format converges into a single Canonical Infrastructure Model, and every downstream engine operates exclusively on that model.

```
Input (.tfstate, .json, .csv, CloudFormation)
    │
    ▼
Parser (format-specific) → ParsedResource (provider-native)
    │
    ▼
Mapper (provider-specific) → CanonicalResource (provider-agnostic)
    │
    ▼
CanonicalInfrastructureGraph
    │
    ├─→ Discovery Engine (tag-based enrichment)
    ├─→ Knowledge Graph Engine (typed dependencies, blast radius)
    ├─→ Translation Engine (capability matrix lookup)
    │       │
    │       ├─→ Assessment Engine (scoring, phasing, blockers)
    │       ├─→ Migration Planner (waves, cutover, confidence)
    │       ├─→ Terraform Generator (GCP HCL output)
    │       └─→ Rollback Planner (destroy order, risk)
    │
    ├─→ Validation Engine (naming, CIDR, dependencies)
    ├─→ Policy Engine (tag/encryption/region/IAM/org checks)
    │       ├─→ Security Engine (IAM, secrets, firewalls)
    │       └─→ Compliance Engine (CIS, NIST, SOC2, PCI, ISO, HIPAA)
    │
    ├─→ FinOps Engine (cost estimation, rightsizing, savings)
    ├─→ AI Engine (explanation, risk analysis, optimization)
    └─→ Reporting Engine (Markdown, JSON, HTML)
```

## Key design invariants

1. **No code path ever generates Terraform from raw input.** Every parser normalizes to `CanonicalResource` first. This is what keeps N input formats and M target providers an N+M problem instead of N×M.

2. **AI advises, rules decide.** Translation decisions, cost estimates, and compliance verdicts come from deterministic engines. The AI layer explains and suggests but never produces authoritative mappings.

3. **Explainability is a schema field.** Every `TranslationRule` has a mandatory `rationale` field validated at load time. The schema rejects "TBD" / "TODO" / "N/A". You cannot add a rule without explaining why it exists.

4. **Plugins are packaging, not code changes.** Parsers, mappers register via `pyproject.toml` entry points. Adding a new input format is a packaging change, not a core code change.

## Adding a new parser

1. Create `src/migration_factory/parsers/my_format.py`:

```python
from migration_factory.parsers.base import BaseParser, ParserResult

class MyFormatParser(BaseParser):
    name = "my_format"

    def supports(self, source_path: Path) -> bool:
        return source_path.suffix == ".myext"

    def parse(self, source_path: Path) -> ParserResult:
        # Parse file -> list of ParsedResource
        ...
```

2. Register in `pyproject.toml`:

```toml
[project.entry-points."migration_factory.parsers"]
my_format = "migration_factory.parsers.my_format:MyFormatParser"
```

3. `pip install -e .` — the plugin manager discovers it automatically.

## Adding a new mapper

1. Create `src/migration_factory/mappers/gcp_to_canonical.py`:

```python
from migration_factory.mappers.base import BaseMapper

class GCPToCanonicalMapper(BaseMapper):
    name = "gcp_to_canonical"

    def supports(self, source_type: str) -> bool:
        return source_type.startswith("google_")

    def map(self, parsed: ParsedResource) -> CanonicalResource:
        ...
```

2. Register in `pyproject.toml`:

```toml
[project.entry-points."migration_factory.mappers"]
gcp_to_canonical = "migration_factory.mappers.gcp_to_canonical:GCPToCanonicalMapper"
```

## Adding a new policy check

1. Add a check function to `policy/engine.py`:

```python
def check_my_rule(resource, graph, policy, parameters):
    if some_condition:
        return _finding(policy, resource, PolicyStatus.FAIL, "Violation message")
    return _finding(policy, resource, PolicyStatus.PASS, "All good")

CHECK_IMPLEMENTATIONS["my_category.my_check"] = check_my_rule
```

2. Add a `PolicyDefinition` to `DEFAULT_POLICIES` (or load from a JSON pack).

## Adding a capability matrix rule

Edit `src/migration_factory/translation/data/aws_to_gcp.json`:

```json
{
  "canonical_type": "compute.container_cluster",
  "target_service": "GKE",
  "target_terraform_types": ["google_container_cluster"],
  "status": "partial",
  "required_changes": ["..."],
  "manual_actions": ["..."],
  "rationale": "Real explanation, not TBD",
  "complexity_weight": 8
}
```

The schema enforces: `rationale` must be >= 10 chars and not a placeholder. `complexity_weight` must be 1-10.

## Testing

```bash
pytest                          # all tests
pytest tests/unit/              # unit only
pytest tests/integration/       # integration only
pytest -k "test_security"       # pattern match
pytest --cov-fail-under=85      # enforce coverage gate
```

Every engine is independently testable because every engine takes a `CanonicalInfrastructureGraph` — no database, no network, no file system required.

## Code standards

- Python 3.11+, type hints everywhere, `mypy --strict`
- Pydantic v2 for models, `extra="forbid"` on all models
- `structlog` for structured JSON logging
- `ruff` for linting (line length 140, ANN rules in src, relaxed in tests)
- Every exception carries `error_code`, `context`, `remediation`
- No global state except the settings singleton (accessed via `get_settings()`)
- Composition over inheritance (see `Container` for DI)
