# User Guide

## Installation

```bash
git clone <repo-url> && cd migration-factory
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # includes test/lint tools
pip install -e ".[ai]"         # includes httpx for AI features
```

## Quick start: analyze a Terraform state file

```bash
# 1. Run the ingestion pipeline
migration-factory ingest terraform.tfstate --output report.json

# 2. View the report
cat report.json | python -m json.tool
```

## Full migration analysis (Python)

```python
from pathlib import Path
from migration_factory.core.config import Settings
from migration_factory.pipeline import IngestionPipeline
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.security.engine import SecurityEngine
from migration_factory.compliance.engine import ComplianceEngine
from migration_factory.finops.engine import FinOpsEngine
from migration_factory.validation.engine import ValidationEngine
from migration_factory.terraform_gen.engine import TerraformGenerator
from migration_factory.planner.engine import MigrationPlanner
from migration_factory.rollback.engine import RollbackPlanner
from migration_factory.discovery.engine import DiscoveryEngine
from migration_factory.knowledge_graph.engine import KnowledgeGraphEngine
from migration_factory.reporting.engine import ReportingEngine
from migration_factory.domain.enums import CloudProvider

# Step 1: Ingest
ingestion = IngestionPipeline().run(Path("terraform.tfstate"))
graph = ingestion.graph

# Step 2: Enrich with business metadata
DiscoveryEngine().enrich(graph)

# Step 3: Build knowledge graph
kg = KnowledgeGraphEngine().analyze(graph)

# Step 4: Translate (AWS → GCP)
matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
translation = TranslationEngine(matrix=matrix).translate(graph)

# Step 5: Assess
assessment = AssessmentEngine().assess(graph, translation)
print(f"Complexity: {assessment.overall_complexity_score}/100")
print(f"Risk: {assessment.risk_level.value}")
print(f"Blockers: {len(assessment.blockers)}")

# Step 6: Validate
validation = ValidationEngine().validate(graph)

# Step 7: Security, Compliance, FinOps
security = SecurityEngine().analyze(graph)
compliance = ComplianceEngine().evaluate(graph)
finops = FinOpsEngine().analyze(graph)
print(f"Security score: {security.security_score}/100")
print(f"Compliance: {compliance.overall_compliance_score}%")
print(f"Monthly savings: ${finops.cost_summary.monthly_savings}")

# Step 8: Plan
plan = MigrationPlanner().plan(graph, assessment, translation)
print(f"Confidence: {plan.confidence.overall_confidence}/100")
print(f"Waves: {len(plan.waves)}")
print(f"Downtime: {plan.cutover_plan.total_downtime_minutes} minutes")

# Step 9: Generate Terraform
gen = TerraformGenerator(project_id="my-gcp-project")
tf_report = gen.generate(graph, translation)
gen.write(tf_report, Path("./terraform-output"))

# Step 10: Rollback plan
rollback = RollbackPlanner().plan(graph, translation)

# Step 11: Generate report
report = ReportingEngine().generate(
    assessment=assessment, translation=translation,
    security=security, compliance=compliance,
    finops=finops, validation=validation, terraform=tf_report,
)
Path("migration-report.md").write_text(report.to_markdown())
html = ReportingEngine().to_html(report)
Path("migration-report.html").write_text(html)
```

## Supported input formats

| Format | Parser | File extension | Auto-detected |
|--------|--------|---------------|--------------|
| Terraform state | `terraform_state` | `.tfstate`, `.json` | Yes (by `format_version` + `resources` keys) |
| Terraform plan | `terraform_plan` | `.json` | Yes (by `resource_changes` key) |
| CloudFormation | `cloudformation` | `.json`, `.yaml`, `.template` | Yes (by `AWSTemplateFormatVersion` or `Resources` key) |
| JSON inventory | `json_inventory` | `.json` | Yes (by `inventory` or `resources` key with list value) |
| CSV inventory | `csv_inventory` | `.csv`, `.tsv` | By extension |

## Understanding the reports

### Complexity score (1-100)

Higher = harder to migrate. Decomposed into three factors visible in `ScoreBreakdown`:
- **Base complexity**: how many target resources does this source resource fan out to
- **Dependency load**: how many dependencies does this resource have (4 pts each, capped at 20)
- **Support penalty**: fully supported = 0, partial = +15, manual = +30, unsupported = +40

### Migration strategy

| Strategy | Meaning |
|----------|---------|
| `rehost` | Clean 1:1 mapping, automated |
| `replatform` | Mapping exists but needs adaptation |
| `manual` | Human redesign required |

### Confidence score (0-100)

Weighted average of: translation coverage (30%), blocker impact (25%), complexity (25%), automation level (20%).

### Security score (0-100)

Higher = more secure. Deductions: -15 per critical finding, -8 per high finding. Based on policy evaluation + IAM analysis + secret scanning + firewall review.

## Configuration

All configuration is via environment variables with the `MF_` prefix. See the API Reference for the full list. No configuration files are required — defaults are sane for development. For production, set `MF_ENVIRONMENT=prod` and `MF_LOGGING__FORMAT=json`.
