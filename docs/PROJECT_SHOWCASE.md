# Migration Factory — Project Showcase
## AI-Powered Multi-Cloud Infrastructure Migration Platform

### What it does in 4 seconds

Upload any Terraform state file → get a complete migration plan:

| Output | Detail |
|--------|--------|
| Complexity score | 1–100 with risk assessment |
| Security analysis | IAM, firewalls, secrets (score 0–100) |
| Compliance | CIS, NIST, SOC2, PCI-DSS, ISO27001, HIPAA |
| FinOps | Current vs target cost, monthly savings |
| Migration waves | Ordered deployment plan, parallel optimization |
| Terraform HCL | Ready-to-review GCP or AWS output |
| HTML report | Shareable stakeholder report |

### Real-world validation

Tested against a live corporate AWS account (SecureKloud):
- 41 real EC2 instances analyzed
- $410/month GCP savings identified
- 5-minute estimated downtime
- 0 migration blockers
- 98/100 confidence score

### 4 use cases

| Use Case | Input | Output |
|----------|-------|--------|
| AWS → GCP | .tfstate / .json / .csv | GCP Terraform HCL |
| GCP → AWS | GCP .tfstate | AWS Terraform HCL |
| AWS analysis | Any AWS inventory | Security + compliance + FinOps |
| GCP analysis | Any GCP inventory | Security + compliance + FinOps |

### Technical architecture

14-stage pipeline:
Ingestion → Discovery → Knowledge Graph → Translation → Assessment
→ Security → Compliance → FinOps → Validation → Drift Analysis
→ Planning → Terraform Gen → Reporting → AI Analysis

(Terraform Gen is skipped in analyze-only mode — 13 stages in that path.)

### Stack

| Layer | Technology |
|-------|-----------|
| Core pipeline | Python 3.11+, Pydantic v2, structlog |
| REST API | FastAPI, uvicorn, SQLAlchemy async |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Frontend | React 19, Vite, Tailwind CSS, JetBrains Mono |
| IaC output | Terraform HCL (GCP + AWS providers) |
| AI analysis | Anthropic Claude (fallback: rule-based) |
| Testing | pytest, 381 tests, 82% coverage |
| CI | GitHub Actions (ruff + mypy + pytest + build) |

### Key numbers

- 381 tests passing
- 82% code coverage
- 58 bidirectional translation rules (29 AWS→GCP + 29 GCP→AWS)
- 34 Terraform generators (18 GCP + 16 AWS)
- 12 input parsers (Terraform state, plan, HCL, and log; CloudFormation;
  ARM templates; ServiceNow CMDB; CSV and Excel inventories; JSON
  inventories; live AWS CLI and GCP CLI output)
- 9 REST API endpoints
- 23 compliance policy checks spanning 6 frameworks (CIS: 11, NIST: 11,
  SOC2: 7, ISO27001: 5, PCI-DSS: 4, HIPAA: 2 — a single check often
  satisfies several frameworks at once, e.g. "encryption at rest" maps to
  all six)
- 6 compliance frameworks (CIS, NIST, SOC2, PCI-DSS, ISO27001, HIPAA)

### API

```bash
# Analyze infrastructure
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "file=@terraform.tfstate" \
  -F "target=gcp"

# Discover live AWS resources
curl http://localhost:8000/api/v1/discover/aws?region=ap-south-1

# Download generated Terraform
curl http://localhost:8000/api/v1/terraform/{run_id} --output terraform.zip

# Swagger UI
open http://localhost:8000/docs
```

### CLI

```bash
# Full migration analysis
migration-factory poc infra.tfstate --target gcp --output ./output

# Specific workflows
migration-factory workflow security infra.tfstate
migration-factory workflow compliance infra.tfstate
migration-factory workflow terraform infra.tfstate --target gcp
```

### GitHub

https://github.com/Prem-G01/migration-factory

---
*Built at SecureKloud · Python · FastAPI · React 19 · Terraform · AWS · GCP*
