# Blog Post Outline
## "How I built an AI-powered AWS↔GCP migration tool in Python"

### Hook (100 words)
Cloud migrations routinely run over budget and past deadline. Most tools
tell you *what* to migrate but not whether it's safe, what it will cost,
or what order to do it in. I built a platform that answers all three in
seconds, for infrastructure moving in either direction between AWS and GCP.

### Section 1: The problem (200 words)
- Manual migration assessments take weeks
- Security and compliance gaps discovered too late
- Cost surprises after migration
- No clear migration order (dependency hell)

### Section 2: Architecture (400 words)
- Pipeline diagram: parse → discover → translate → assess → secure →
  comply → cost → validate → plan → generate Terraform → report
- Canonical resource model (29 provider-agnostic types)
- Translation matrix concept
- Why rules need rationale, not just mappings

### Section 3: The hardest parts (500 words)
- AWS SG vs GCP Firewall rule model difference
- IAM permission model mismatch
- Detecting Windows vs Linux instances from partial metadata
  (Platform field, AMI name, tags — in that reliability order)
- Making CSV/Excel "just work" with any column names
- A real bug this surfaced: an availability-zone check with an operator-
  precedence mistake silently collapsed every non-US AWS zone to a single
  default GCP zone — worth a section on why this class of bug is easy to
  miss and how testing against a real (not synthetic) inventory caught it

### Section 4: What I learned (300 words)
- Pydantic v2 for strict domain models
- structlog for structured logging
- Why coverage on a pipeline's error paths matters more than the headline percentage
- FastAPI + React for a full-stack demo

### Section 5: Results + what's next (200 words)
- 41 real instances analyzed, $410/mo savings found
- What production-grade would add next (real state backend, live plan/apply
  against a target project, broader canonical-type coverage)
- GitHub link
