"""Native PDF Report Renderer.

Multi-strategy PDF generation:
1. weasyprint (best quality, needs cairo/pango system deps)
2. reportlab (pure Python, no system deps, good quality)
3. HTML file fallback (always works, printable from browser)

Auto-detects which strategy is available and uses the best one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from migration_factory.core.logging import get_logger
from migration_factory.reporting.engine import MigrationReport, ReportingEngine

logger = get_logger(__name__)


class PDFStrategy:
    WEASYPRINT = "weasyprint"
    REPORTLAB = "reportlab"
    HTML_FALLBACK = "html_fallback"


def _detect_strategy() -> str:
    """Auto-detect the best available PDF strategy."""
    try:
        import weasyprint  # noqa: F401
        return PDFStrategy.WEASYPRINT
    except (ImportError, OSError):
        pass
    try:
        import reportlab  # noqa: F401
        return PDFStrategy.REPORTLAB
    except ImportError:
        pass
    return PDFStrategy.HTML_FALLBACK


def _strip_html(text: str) -> str:
    """Strip HTML tags for plain text extraction."""
    return re.sub(r"<[^>]+>", "", text).strip()


@dataclass(slots=True)
class NativePDFRenderer:
    """Auto-selecting PDF renderer. Uses the best available strategy."""

    strategy: str | None = None

    def __post_init__(self) -> None:
        if self.strategy is None:
            self.strategy = _detect_strategy()

    def render(self, report: MigrationReport, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("pdf_render_started", strategy=self.strategy, output=str(output_path))

        if self.strategy == PDFStrategy.WEASYPRINT:
            return self._render_weasyprint(report, output_path)
        if self.strategy == PDFStrategy.REPORTLAB:
            return self._render_reportlab(report, output_path)
        return self._render_html_fallback(report, output_path)

    @staticmethod
    def _render_weasyprint(report: MigrationReport, output_path: Path) -> Path:
        from weasyprint import HTML
        reporting_engine = ReportingEngine()
        html = reporting_engine.to_html(report)
        HTML(string=html).write_pdf(str(output_path))
        logger.info("pdf_rendered_weasyprint", output=str(output_path))
        return output_path

    @staticmethod
    def _render_reportlab(report: MigrationReport, output_path: Path) -> Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                                leftMargin=2 * cm, rightMargin=2 * cm,
                                topMargin=2 * cm, bottomMargin=2 * cm)
        styles = getSampleStyleSheet()
        story = []

        # Title
        story.append(Paragraph(report.title, styles["Title"]))
        story.append(Paragraph(f"Generated: {report.generated_at}", styles["Normal"]))
        story.append(Spacer(1, 0.5 * cm))

        # Sections
        for section in report.sections:
            story.append(Paragraph(section.title, styles["Heading1"]))
            story.append(Spacer(1, 0.2 * cm))

            lines = section.content.split("\n")
            table_rows: list[list[str]] = []
            in_table = False

            for line in lines:
                if line.startswith("|") and "|" in line[1:]:
                    if line.strip().startswith("|---") or line.strip().startswith("| ---"):
                        continue
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    table_rows.append(cells)
                    in_table = True
                else:
                    if in_table and table_rows:
                        table = Table(table_rows)
                        table.setStyle(TableStyle([
                            ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                        ]))
                        story.append(table)
                        story.append(Spacer(1, 0.3 * cm))
                        table_rows = []
                        in_table = False

                    clean = _strip_html(line)
                    if clean:
                        if line.startswith("###"):
                            story.append(Paragraph(clean.lstrip("#").strip(), styles["Heading3"]))
                        elif line.startswith("##"):
                            story.append(Paragraph(clean.lstrip("#").strip(), styles["Heading2"]))
                        elif line.startswith("- "):
                            story.append(Paragraph(f"• {clean[2:]}", styles["Normal"]))
                        elif clean:
                            story.append(Paragraph(clean, styles["Normal"]))

            if in_table and table_rows:
                table = Table(table_rows)
                story.append(table)

            story.append(Spacer(1, 0.5 * cm))

        doc.build(story)
        logger.info("pdf_rendered_reportlab", output=str(output_path))
        return output_path

    @staticmethod
    def _render_html_fallback(report: MigrationReport, output_path: Path) -> Path:
        """Save as print-optimized HTML when no PDF library is available."""
        reporting_engine = ReportingEngine()
        html = reporting_engine.to_html(report)
        print_css = """
        <style>
          @media print {
            body { font-size: 10pt; }
            h1 { page-break-before: always; }
            h1:first-child { page-break-before: avoid; }
            table { page-break-inside: avoid; }
          }
        </style>"""
        html = html.replace("</head>", f"{print_css}</head>")
        html_path = output_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        logger.info("pdf_fallback_html", output=str(html_path))
        return html_path
