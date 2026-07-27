# Migration Factory — 2-Minute Demo Script

## Setup (before demo)

```
Terminal 1: uvicorn migration_factory.api.main:app --port 8000
Terminal 2: cd frontend && npm run dev
Browser:    http://localhost:5173
```

## Demo flow (2 minutes)

**[0:00]** Open http://localhost:5173
"This is Migration Factory — an AI-powered platform that analyzes
cloud infrastructure and generates migration plans in seconds."

**[0:15]** Drag `tests/fixtures/complex_terraform.tfstate` onto the upload zone
"I'll use this complex AWS estate — 31 resources including EC2, RDS,
Lambda, EKS, S3, and load balancers."

**[0:25]** Select "Migrate to GCP", click Analyze
"Selecting GCP as the target. The pipeline is now running..."

**[0:35]** Results appear
"Complexity score 34/100, risk HIGH, 58% migration confidence,
$107/month savings. 8 migration waves, 35 minutes downtime."

**[0:50]** Point to compliance bars
"Compliance across 6 frameworks — CIS and NIST pass, SOC2 needs work."

**[1:00]** Click Download Terraform
"7 Terraform files generated — ready to review and apply."

**[1:10]** Click View Full Report
"Full HTML report for stakeholders — complexity, security, cost analysis."

**[1:20]** Click History
"Every run persisted in the database. Teams can share one instance."

**[1:30]** Open http://localhost:8000/docs
"Full REST API with Swagger UI — CI/CD pipelines can call this directly."

**[1:45]** Show terminal — migration-factory poc command
"Or use the CLI: migration-factory poc infra.tfstate --target gcp"

**[2:00]** Done.

## Key numbers to mention

- 381 tests, 84% coverage
- 58 translation rules (AWS↔GCP bidirectional)
- 4 use cases: AWS→GCP, GCP→AWS, AWS-only, GCP-only
- Validated on a real AWS account: 41 instances, $410/month savings identified
- 18 GCP Terraform generators, 16 AWS Terraform generators
- 12 input parsers: Terraform state, Terraform plan, Terraform HCL,
  Terraform log, CloudFormation, ARM template, CSV, Excel, JSON inventory,
  ServiceNow CMDB, raw AWS CLI JSON, raw gcloud CLI JSON
- 7 REST API endpoints
