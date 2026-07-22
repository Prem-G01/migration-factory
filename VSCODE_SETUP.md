# Migration Factory — VS Code Setup & Testing Guide

## Prerequisites

Install these before starting:

| Tool | Download | Version |
|------|----------|---------|
| VS Code | https://code.visualstudio.com | Latest |
| Python | https://python.org/downloads | 3.11 or higher |
| Git | https://git-scm.com | Latest |

---

## Step 1 — Get the Code

### Option A: From the zip file (you have this)

1. Download `migration-factory-poc-v2.0.2.zip`
2. Right-click → Extract All → choose a folder like `C:\Projects\` or `~/Projects/`
3. You should now have: `~/Projects/migration-factory/`

### Option B: From Git

```bash
git clone <your-repo-url>
cd migration-factory
```

---

## Step 2 — Open in VS Code

1. Open VS Code
2. **File** → **Open Folder**
3. Select the `migration-factory` folder
4. VS Code opens — you'll see the file tree on the left

You should see this structure:
```
migration-factory/
├── src/
│   └── migration_factory/
│       ├── ai/
│       ├── assessment/
│       ├── cli.py          ← main entry point
│       ├── pipeline.py
│       └── ...
├── tests/
│   ├── fixtures/
│   │   └── sample_terraform.tfstate  ← test input
│   └── unit/
├── docs/
├── HOW_IT_WORKS.md
├── pyproject.toml
└── README.md
```

---

## Step 3 — Install VS Code Extensions

Click the **Extensions icon** (Ctrl+Shift+X) and install:

| Extension | Publisher | Why |
|-----------|-----------|-----|
| Python | Microsoft | Python language support |
| Pylance | Microsoft | Type checking, autocomplete |
| Python Test Explorer | LittleFoxTeam | Run tests with UI |
| HashiCorp Terraform | HashiCorp | Syntax highlight for generated .tf files |
| Markdown Preview | Built-in | View migration reports |

---

## Step 4 — Create Python Virtual Environment

Open the **Terminal** in VS Code:
- **Terminal** → **New Terminal** (or `Ctrl+\``)

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Mac / Linux
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` at the start of your terminal prompt.

---

## Step 5 — Install the Package

In the terminal (with .venv active):

```bash
pip install -e ".[dev]"
```

Wait ~30 seconds. You'll see packages installing.

**Verify it worked:**
```bash
migration-factory --help
```

Expected output:
```
usage: migration-factory [-h] {ingest,poc} ...

AI-Powered Multi-Cloud Infrastructure Migration Factory

positional arguments:
  {ingest,poc}
    ingest       Parse + normalize a single input file
    poc          Full AWS↔GCP migration POC
```

---

## Step 6 — Select Python Interpreter

1. Press **Ctrl+Shift+P** → type `Python: Select Interpreter`
2. Choose the one with `.venv` in the path:
   - Windows: `.venv\Scripts\python.exe`
   - Mac/Linux: `.venv/bin/python`

You'll see it appear in the bottom status bar.

---

## Step 7 — Run Your First POC

In the terminal:

```bash
migration-factory poc tests/fixtures/sample_terraform.tfstate --target gcp --output ./output
```

Watch the terminal — it runs the full 12-stage pipeline and shows:

```
╭──────────────────────────────────────────────────╮
│ Migration Factory  AI-Powered Migration          │
│ Source: sample_terraform.tfstate  Target: GCP    │
╰──────────────────────────────────────────────────╯

╭──────────── Executive Summary ───────────────────╮
│ Migration              AWS → GCP                 │
│ Resources discovered   6                         │
│ Complexity score       27/100                    │
│ Risk level             MEDIUM                    │
│ Migration confidence   72/100                    │
│ Monthly savings        $13                       │
│ Estimated downtime     5 minutes                 │
│ Migration waves        5                         │
│ Blockers               3                         │
╰──────────────────────────────────────────────────╯
```

---

## Step 8 — View Output Files

After running, check the `output/` folder in VS Code's file tree:

```
output/
├── terraform/
│   ├── main.tf          ← Generated GCP Terraform
│   ├── variables.tf
│   ├── outputs.tf
│   ├── providers.tf
│   ├── versions.tf
│   ├── backend.tf
│   └── terraform.tfvars
├── migration-report.md
├── migration-report.html
└── dependency-graph.mmd
```

### View the Terraform

Click `output/terraform/main.tf` — you'll see real GCP HCL:

```hcl
resource "google_compute_network" "aws_vpc_main" {
  name                    = var.aws_vpc_main_name
  auto_create_subnetworks = false
  description             = "Migrated from aws_vpc: vpc-0abc123"
}

resource "google_compute_firewall" "aws_security_group_app" {
  name    = var.aws_security_group_app_name
  network = google_compute_network.main.name

  allow {
    protocol = "tcp"
    ports    = ["443", "80"]
  }

  source_ranges = ["10.0.0.0/8"]
}
```

### View the HTML Report

1. Right-click `output/migration-report.html`
2. Select **Open with Live Server** (if extension installed)
   OR
3. Copy the full path and open in your browser

### View the Dependency Diagram

1. Open `output/dependency-graph.mmd`
2. Go to https://mermaid.live
3. Paste the content → you'll see a visual dependency graph

---

## Step 9 — Run the Test Suite

### Option A: From terminal

```bash
# Run all 328 tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/unit/test_assessment.py -v

# Run with coverage report
pytest --cov=migration_factory --cov-report=html
```

After `--cov-report=html`, open `htmlcov/index.html` in your browser for a coverage report.

### Option B: From VS Code Test UI

1. Click the **Testing icon** (flask icon) in the left sidebar
2. Click **Configure Python Tests**
3. Select **pytest**
4. Select `tests/` as the test directory
5. Click the **Run All Tests** button (▶▶)

You'll see green ✓ for passing, red ✗ for failing.

---

## Step 10 — Test With Your Own State File

If you have a real AWS Terraform project:

```bash
# Export your current state
cd /path/to/your/terraform/project
terraform state pull > my-real-infra.tfstate

# Copy it to the migration-factory folder
cp my-real-infra.tfstate ~/Projects/migration-factory/

# Run the POC
cd ~/Projects/migration-factory
migration-factory poc my-real-infra.tfstate --target gcp --output ./my-output
```

---

## Step 11 — Run Individual Engines (Advanced)

Open VS Code's **integrated Python** (Ctrl+Shift+P → `Python: Create Interactive Window`):

```python
# Test just the translation engine
from pathlib import Path
from migration_factory.core.config import Settings
from migration_factory.pipeline import IngestionPipeline
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
from migration_factory.domain.enums import CloudProvider

# Load the sample file
settings = Settings()
ingestion = IngestionPipeline(settings=settings).run(
    Path("tests/fixtures/sample_terraform.tfstate")
)
print(f"Parsed {len(ingestion.graph.resources)} resources")

# Translate to GCP
matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
translation = TranslationEngine(matrix=matrix).translate(ingestion.graph)
print(f"Translation summary: {translation.summary}")

# Check each resource
for result in translation.results:
    print(f"  {result.resource_name}: {result.status.value} → {result.target_service}")
```

---

## Step 12 — Debug Mode

Set a breakpoint and step through the code:

1. Open `src/migration_factory/assessment/engine.py`
2. Click in the left margin on line 1 to set a breakpoint (red dot appears)
3. Open `.vscode/launch.json` (create if not exists):

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Run POC",
            "type": "debugpy",
            "request": "launch",
            "module": "migration_factory.cli",
            "args": [
                "poc",
                "tests/fixtures/sample_terraform.tfstate",
                "--target", "gcp",
                "--output", "./output"
            ],
            "env": {
                "MF_LOGGING__FORMAT": "console",
                "MF_LOGGING__LEVEL": "DEBUG"
            }
        },
        {
            "name": "Run Tests",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["-v", "tests/unit/test_assessment.py"]
        }
    ]
}
```

4. Press **F5** to start debugging
5. The code will pause at your breakpoint
6. Use **F10** (step over), **F11** (step into), **F5** (continue)

---

## Common Issues & Fixes

### Issue: `migration-factory: command not found`
```bash
# Make sure venv is active
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate       # Windows

# Reinstall
pip install -e .
```

### Issue: `ModuleNotFoundError: No module named 'migration_factory'`
```bash
pip install -e ".[dev]"
```

### Issue: Tests fail with import errors
```bash
# Check Python interpreter is the venv one
which python   # should show .venv path
pip install -e ".[dev]"
```

### Issue: `openpyxl` or `pyhcl2` not found
```bash
pip install openpyxl python-hcl2
```

### Issue: Output folder not created
```bash
# Create it manually
mkdir output
migration-factory poc tests/fixtures/sample_terraform.tfstate --target gcp --output ./output
```

---

## What Each File Does

| File | Purpose |
|------|---------|
| `src/migration_factory/cli.py` | The `migration-factory` command — start here |
| `src/migration_factory/pipeline.py` | Wires parsers + mappers together |
| `src/migration_factory/parsers/terraform_state.py` | Reads .tfstate files |
| `src/migration_factory/mappers/aws_to_canonical.py` | Maps aws_* to canonical types |
| `src/migration_factory/translation/engine.py` | AWS→GCP capability matrix lookup |
| `src/migration_factory/assessment/engine.py` | Scores complexity + risk |
| `src/migration_factory/security/engine.py` | IAM, secrets, firewall analysis |
| `src/migration_factory/finops/engine.py` | Cost estimation |
| `src/migration_factory/terraform_gen/engine.py` | Generates GCP .tf files |
| `src/migration_factory/planner/engine.py` | Wave planning + cutover |
| `tests/fixtures/sample_terraform.tfstate` | 6-resource AWS sample — test input |
| `HOW_IT_WORKS.md` | Architecture and API reference |

---

## Checklist

- [ ] VS Code installed
- [ ] Python 3.11+ installed (`python --version`)
- [ ] Folder opened in VS Code
- [ ] Python + Pylance extensions installed
- [ ] Virtual environment created (`.venv/`)
- [ ] Package installed (`pip install -e ".[dev]"`)
- [ ] Python interpreter set to `.venv`
- [ ] `migration-factory --help` works
- [ ] POC command produces terminal output
- [ ] `output/terraform/main.tf` exists and has GCP resources
- [ ] `pytest` shows 328 passed
- [ ] HTML report opens in browser
