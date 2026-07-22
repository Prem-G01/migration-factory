# Migration Factory — How It Works & How to Test

## Quick Start (3 commands)

```bash
# 1. Install
git clone <repo> && cd migration-factory
pip install -e .

# 2. Run POC on sample data (works immediately, no credentials needed)
migration-factory poc tests/fixtures/sample_terraform.tfstate --target gcp --output ./output

# 3. See what was generated
ls output/terraform/
cat output/migration-report.md
```

---

## How It Works — End to End

### What happens when you run `migration-factory poc`

```
Your .tfstate file
        │
        ▼
┌─────────────────┐
│  1. PARSE       │  Reads .tfstate → extracts raw AWS resources
│  TfStateParser  │  (VPC, subnet, EC2, SG, S3, IAM role...)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. NORMALIZE   │  Maps aws_instance → CanonicalResource{compute.instance}
│  AWSMapper      │  Strips provider-specific fields → cloud-agnostic model
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  3. ENRICH      │  Tags → owner, environment, criticality, application
│  DiscoveryEngine│  Fills business metadata from resource tags
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  4. GRAPH       │  Builds dependency graph (VPC → Subnet → EC2)
│  KnowledgeGraph │  Detects blast radius, critical paths, app groups
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  5. TRANSLATE   │  29-rule capability matrix lookup per resource
│  TranslationEng │  aws_instance → google_compute_instance (SUPPORTED)
└────────┬────────┘  aws_security_group → google_compute_firewall (PARTIAL)
         │           aws_iam_role → google_service_account (MANUAL)
         ▼
┌─────────────────┐
│  6. ASSESS      │  Complexity 1-100, Risk LOW/MEDIUM/HIGH
│  AssessmentEng  │  Phases: Networking → IAM → Storage → Compute
└────────┬────────┘  Blockers, recommendations, confidence score
         │
         ▼
┌─────────────────┐
│  7. SECURITY    │  IAM over-privilege, open SG rules, secrets in state
│  SecurityEngine │  Score 0-100, findings with severity
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  8. COMPLIANCE  │  CIS, NIST, SOC2, PCI-DSS, ISO27001, HIPAA
│  ComplianceEng  │  Score per framework, failed checks
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  9. FINOPS      │  Cost estimate: source vs target, monthly savings
│  FinOpsEngine   │  Break-even calculation, rightsizing suggestions
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  10. PLAN       │  Migration waves (parallel vs sequential)
│  MigrationPlan  │  Cutover steps, downtime estimate, rollback plan
└────────┬────────┘  Confidence score, maintenance window
         │
         ▼
┌─────────────────┐
│  11. GENERATE   │  Real GCP Terraform HCL
│  TerraformGen   │  main.tf, variables.tf, outputs.tf,
└────────┬────────┘  providers.tf, versions.tf, backend.tf
         │
         ▼
┌─────────────────┐
│  12. REPORT     │  Markdown + HTML + Mermaid diagram
│  ReportingEng   │  Executive summary, per-resource tables,
└─────────────────┘  compliance breakdown, recommendations
```

**Time: ~4 seconds. No cloud credentials needed.**

---

## How to Test

### Level 1 — Smoke test (30 seconds)

```bash
# Run the full pipeline on sample data
migration-factory poc tests/fixtures/sample_terraform.tfstate --target gcp --output ./output

# Expected: rich terminal output, then check:
ls output/terraform/     # → 7 .tf files
cat output/terraform/main.tf  # → real GCP HCL (no TODOs)
open output/migration-report.html  # → styled HTML report
```

### Level 2 — Unit tests (60 seconds)

```bash
# Run all 328 tests
pytest

# Run just one engine
pytest tests/unit/test_translation.py -v
pytest tests/unit/test_assessment.py -v
pytest tests/unit/test_security_engine.py -v
pytest tests/unit/test_finops.py -v

# Run with coverage
pytest --cov=migration_factory --cov-report=term-missing
```

### Level 3 — Test with your own Terraform state

```bash
# Export your real AWS state
cd your-terraform-project
terraform state pull > my-infra.tfstate

# Run the POC against it
migration-factory poc my-infra.tfstate --target gcp --output ./my-output

# Or test GCP → AWS direction
migration-factory poc my-gcp.tfstate --target aws --output ./aws-output
```

### Level 4 — Test specific parsers

```bash
# CloudFormation template
migration-factory ingest my-stack.json

# CSV inventory
migration-factory ingest resources.csv

# ARM template (Azure)
migration-factory ingest template.json

# Excel inventory
migration-factory ingest inventory.xlsx

# Terraform plan JSON
terraform plan -out=plan.out
terraform show -json plan.out > plan.json
migration-factory ingest plan.json
```

### Level 5 — Test via Python API

```python
from pathlib import Path
from migration_factory.pipeline import IngestionPipeline
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.security.engine import SecurityEngine
from migration_factory.finops.engine import FinOpsEngine
from migration_factory.terraform_gen.engine import TerraformGenerator
from migration_factory.domain.enums import CloudProvider
from migration_factory.core.config import Settings

# Step 1: Load your state file
settings = Settings()
ingestion = IngestionPipeline(settings=settings).run(Path("my-infra.tfstate"))
graph = ingestion.graph
print(f"Resources: {len(graph.resources)}")

# Step 2: Translate AWS → GCP
matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
translation = TranslationEngine(matrix=matrix).translate(graph)
print(f"Supported: {translation.summary}")

# Step 3: Assess
assessment = AssessmentEngine().assess(graph, translation)
print(f"Complexity: {assessment.overall_complexity_score}/100")
print(f"Risk: {assessment.risk_level.value}")
print(f"Blockers: {len(assessment.blockers)}")

# Step 4: Security
security = SecurityEngine().analyze(graph)
print(f"Security score: {security.security_score}/100")

# Step 5: Cost
finops = FinOpsEngine().analyze(graph)
print(f"Monthly savings: ${finops.cost_summary.monthly_savings:.0f}")

# Step 6: Generate Terraform
gen = TerraformGenerator(project_id="my-gcp-project")
terraform = gen.generate(graph, translation)
gen.write(terraform, Path("./output/terraform"))
print(f"Generated {len(terraform.files)} Terraform files")
```

---

## What Each Output Means

### Terminal output

| Section | What it tells you |
|---------|------------------|
| Executive Summary | Go/no-go signal: complexity, risk, confidence, cost delta |
| Translation Plan | Which resources migrate cleanly vs need manual work |
| Migration Waves | Order and duration — what to deploy first |
| Resource Assessment | Per-resource score, strategy, target service |
| Security Findings | What to fix before migrating |
| Blockers | Hard stops that must be resolved first |
| Compliance | Which frameworks pass/fail |
| Recommendation | One-line verdict |

### Generated files

| File | What to do with it |
|------|--------------------|
| `terraform/main.tf` | Your GCP infrastructure — review, then `terraform apply` |
| `terraform/variables.tf` | Edit defaults to match your naming |
| `terraform/providers.tf` | Set your GCP project ID |
| `terraform/backend.tf` | Configure your state bucket |
| `migration-report.html` | Share with stakeholders |
| `migration-report.md` | Include in migration docs |
| `dependency-graph.mmd` | Paste into [mermaid.live](https://mermaid.live) for visual |

---

## Supported Input Formats

| Format | Command | Example |
|--------|---------|---------|
| Terraform state | auto-detected | `terraform state pull > infra.tfstate` |
| Terraform plan | auto-detected | `terraform show -json plan.out > plan.json` |
| Terraform HCL | auto-detected | `migration-factory poc main.tf` |
| CloudFormation | auto-detected | `migration-factory poc stack.json` |
| ARM Template (Azure) | auto-detected | `migration-factory poc template.json` |
| CSV inventory | auto-detected | type,name,id,provider columns |
| Excel inventory | auto-detected | same columns as CSV |
| JSON inventory | auto-detected | `{"inventory": [...]}` |
| ServiceNow CMDB | auto-detected | `{"result": [...]}` |
| Terraform log | auto-detected | `terraform apply 2>&1 \| tee apply.log` |

---

## Environment Variables

```bash
# Enable AI-powered analysis (optional — works without it)
export ANTHROPIC_API_KEY=sk-ant-...

# Switch to live cloud discovery (optional — simulation works without)
export CLOUD_DISCOVERY_MODE=live
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

# Logging
export MF_LOGGING__LEVEL=INFO        # DEBUG, INFO, WARNING, ERROR
export MF_LOGGING__FORMAT=console    # console (human) or json (production)
export MF_ENVIRONMENT=prod           # dev, staging, prod
```

---

## What's Next After POC

Once the POC proves the concept to stakeholders:

1. **FastAPI layer** — wrap every engine in a REST endpoint, add JWT auth
2. **PostgreSQL** — persist migration runs between sessions
3. **Web dashboard** — React UI with dependency graph, report viewer, AI chat
4. **Live cloud discovery** — add AWS/GCP credentials, flip `simulation=False`
5. **GitOps integration** — auto-create PR with generated Terraform on approval
6. **Slack/Teams alerts** — migration events via the NotificationEngine
