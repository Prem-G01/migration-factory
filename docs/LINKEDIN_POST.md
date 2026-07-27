# LinkedIn Post

🏭 I built an AI-powered multi-cloud infrastructure migration platform from scratch.

**Migration Factory** analyzes cloud infrastructure and generates complete
migration plans in seconds.

Upload a Terraform state file → get:
✅ Complexity score (1–100) with risk assessment
✅ Security analysis across IAM, firewalls, secrets
✅ Compliance check: CIS, NIST, SOC2, PCI-DSS, ISO27001, HIPAA
✅ FinOps analysis: current vs target cost, monthly savings
✅ Migration wave plan with downtime estimate
✅ Generated Terraform HCL — ready to review and apply
✅ HTML + Markdown reports for stakeholders

**4 use cases supported:**
- AWS → GCP migration
- GCP → AWS migration
- AWS estate analysis (no migration target)
- GCP estate analysis (no migration target)

**Validated on real infrastructure:**
41 live EC2 instances → $410/month savings identified in seconds

**Tech stack:**
Python · FastAPI · React 19 · Tailwind CSS · SQLAlchemy async ·
Terraform HCL generation · Pydantic v2 · structlog · pytest

**Numbers:**
381 tests · 84% coverage · 58 bidirectional translation rules ·
12 input formats · 7 REST API endpoints · 4 use cases ·
18 GCP + 16 AWS Terraform generators

🔗 github.com/Prem-G01/migration-factory

What took the most time to get right: the bidirectional translation
matrix. AWS and GCP have fundamentally different resource models —
mapping aws_security_group to google_compute_firewall sounds simple
until you realize AWS SGs are instance-attached and stateful while
GCP firewall rules are VPC-level and tag-based. Every one of the
58 rules has an expert rationale explaining why.

#CloudEngineering #AWS #GCP #DevOps #PlatformEngineering
#Python #Terraform #MultiCloud #AIEngineering #OpenSource
