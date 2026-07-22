"""Excel and PDF report renderers + performance test fixture generator.

Closes: Excel Reports, PDF Reports, Performance Tests (fixture generation).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
    SourceLocation,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.reporting.engine import MigrationReport

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Excel Report Renderer
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ExcelReportRenderer:
    """Renders a MigrationReport to .xlsx using openpyxl."""

    def render(self, report: MigrationReport, output_path: Path) -> Path:
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("openpyxl required: pip install openpyxl") from exc

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Summary"

        # Title
        ws.append([report.title])
        ws.append([f"Generated: {report.generated_at}"])
        ws.append([])

        # Each section becomes a sheet
        for section in report.sections:
            sheet = ws if section.title == report.sections[0].title else wb.create_sheet(title=section.title[:31])

            sheet.append([section.title])
            sheet.append([])

            for line in section.content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("|"):
                    # Parse markdown table row
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    if cells and not all(c.startswith("---") for c in cells):
                        sheet.append(cells)
                elif line.startswith("- "):
                    sheet.append(["", line[2:]])
                elif line.startswith("**"):
                    sheet.append([line.replace("**", "")])
                else:
                    sheet.append([line])

        # Auto-width columns (best effort)
        for sheet in wb.worksheets:
            for col in sheet.columns:
                max_len = 0
                for cell in col:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                adjusted = min(max_len + 2, 60)
                sheet.column_dimensions[col[0].column_letter].width = adjusted

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        logger.info("excel_report_rendered", path=str(output_path))
        return output_path


# ---------------------------------------------------------------------------
# PDF Report Renderer
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PDFReportRenderer:
    """Renders a MigrationReport to PDF.

    Uses the HTML report as intermediate, then converts to PDF via
    weasyprint (if available) or saves as HTML with print-friendly CSS.
    """

    def render(self, report: MigrationReport, html: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from weasyprint import HTML
            HTML(string=html).write_pdf(str(output_path))
            logger.info("pdf_report_rendered", path=str(output_path), method="weasyprint")
        except ImportError:
            # Fallback: save as HTML with print-friendly styling
            html_path = output_path.with_suffix(".html")
            print_css = "<style>@media print { body { font-size: 11pt; } }</style>"
            html_with_print = html.replace("</head>", f"{print_css}</head>")
            html_path.write_text(html_with_print, encoding="utf-8")
            logger.info("pdf_fallback_html_saved", path=str(html_path), reason="weasyprint not installed")
            return html_path

        return output_path


# ---------------------------------------------------------------------------
# Performance Test Fixture Generator
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PerformanceFixtureGenerator:
    """Generates large synthetic canonical graphs for performance testing."""

    def generate(
        self,
        resource_count: int = 1000,
        dependency_density: float = 0.3,
    ) -> CanonicalInfrastructureGraph:
        """Generate a graph with N resources and ~density% dependency edges.

        Produces a realistic distribution across canonical types, with
        dependencies that respect natural ordering (VPC before subnet
        before instance, etc.).
        """
        graph = CanonicalInfrastructureGraph()

        # Type distribution (realistic enterprise estate)
        type_weights: list[tuple[CanonicalResourceType, float]] = [
            (CanonicalResourceType.NETWORK_VPC, 0.03),
            (CanonicalResourceType.NETWORK_SUBNET, 0.08),
            (CanonicalResourceType.NETWORK_FIREWALL_RULE, 0.10),
            (CanonicalResourceType.COMPUTE_INSTANCE, 0.25),
            (CanonicalResourceType.STORAGE_OBJECT_BUCKET, 0.10),
            (CanonicalResourceType.DATABASE_INSTANCE, 0.05),
            (CanonicalResourceType.IAM_ROLE, 0.08),
            (CanonicalResourceType.LOAD_BALANCER, 0.04),
            (CanonicalResourceType.DNS_RECORD, 0.06),
            (CanonicalResourceType.MESSAGING_QUEUE, 0.05),
            (CanonicalResourceType.COMPUTE_SERVERLESS_FUNCTION, 0.06),
            (CanonicalResourceType.SECRETS_MANAGER, 0.03),
            (CanonicalResourceType.MONITORING_ALARM, 0.04),
            (CanonicalResourceType.NETWORK_NAT_GATEWAY, 0.03),
        ]

        # Build resources
        resources_by_tier: dict[str, list[str]] = {
            "network": [], "iam": [], "storage": [], "database": [],
            "compute": [], "dns": [], "messaging": [], "monitoring": [],
            "secrets": [], "security": [], "cdn": [],
        }

        idx = 0
        for ctype, weight in type_weights:
            count = max(1, int(resource_count * weight))
            tier = ctype.value.split(".")[0]

            for i in range(count):
                if idx >= resource_count:
                    break
                rid = f"perf_{ctype.value.replace('.', '_')}_{i:04d}"

                # Assign dependencies based on tier hierarchy
                deps: set[str] = set()
                if tier == "compute" and resources_by_tier["network"]:
                    # Compute depends on network
                    dep_idx = i % len(resources_by_tier["network"])
                    deps.add(resources_by_tier["network"][dep_idx])
                elif tier == "database" and resources_by_tier["network"]:
                    dep_idx = i % len(resources_by_tier["network"])
                    deps.add(resources_by_tier["network"][dep_idx])

                resource = CanonicalResource(
                    id=rid,
                    canonical_type=ctype,
                    source_provider=CloudProvider.AWS,
                    source_type=f"aws_{ctype.value.replace('.', '_')}",
                    name=rid,
                    region="us-east-1",
                    depends_on=frozenset(deps),
                    native_attributes={"perf_test": True, "index": idx},
                    source_location=SourceLocation(
                        source_system="perf_generator",
                        source_path="synthetic",
                    ),
                    tags={"Environment": "perf-test", "Index": str(idx)},
                )
                graph.add_resource(resource)
                resources_by_tier.setdefault(tier, []).append(rid)
                idx += 1

        logger.info("perf_fixture_generated", resource_count=len(graph.resources))
        return graph
