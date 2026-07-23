"""Terraform HCL Parser, Terraform Log Parser, and Excel Inventory Parser.

Completes the parser suite: every input format in the original spec now has
a working parser registered via entry points.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from migration_factory.core.exceptions import ParserError
from migration_factory.core.logging import get_logger
from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.base import BaseParser, ParsedResource, ParserResult, ParseWarning
from migration_factory.parsers.column_detection import build_resource_from_row

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Terraform HCL Parser (.tf files)
# ---------------------------------------------------------------------------


class TerraformHCLParser(BaseParser):
    """Parses Terraform .tf HCL source files using pyhcl2."""

    name = "terraform_hcl"

    def supports(self, source_path: Path) -> bool:
        return source_path.suffix == ".tf"

    def parse(self, source_path: Path) -> ParserResult:
        try:
            import hcl2
        except ImportError as exc:
            raise ParserError(
                "python-hcl2 is required for HCL parsing: pip install python-hcl2",
                context={"source_path": str(source_path)},
                cause=exc,
            ) from exc

        try:
            with source_path.open(encoding="utf-8") as f:
                parsed = hcl2.load(f)
        except Exception as exc:
            raise ParserError(
                f"Could not parse HCL file: {source_path}",
                context={"source_path": str(source_path)},
                cause=exc,
            ) from exc

        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []

        def _strip_quotes(s: str) -> str:
            return s.strip('"').strip("'") if isinstance(s, str) else str(s)

        for resource_block in parsed.get("resource", []):
            if not isinstance(resource_block, dict):
                continue
            for resource_type_raw, instances in resource_block.items():
                resource_type = _strip_quotes(resource_type_raw)
                if not isinstance(instances, dict):
                    continue
                for resource_name_raw, body in instances.items():
                    resource_name = _strip_quotes(resource_name_raw)
                    if not isinstance(body, dict):
                        continue

                    # Clean up quoted keys/values from python-hcl2
                    clean_body = {
                        _strip_quotes(k): _strip_quotes(v) if isinstance(v, str) else v
                        for k, v in body.items() if k != "__is_block__"
                    }

                    address = f"{resource_type}.{resource_name}"
                    provider = CloudProvider.UNKNOWN
                    if resource_type.startswith("aws_"):
                        provider = CloudProvider.AWS
                    elif resource_type.startswith("google_"):
                        provider = CloudProvider.GCP

                    depends = clean_body.get("depends_on", [])
                    if not isinstance(depends, list):
                        depends = []

                    resources.append(ParsedResource(
                        source_provider=provider,
                        source_type=resource_type,
                        source_identifier=address,
                        name=str(clean_body.get("name", clean_body.get("bucket", resource_name))),
                        attributes=clean_body,
                        raw_depends_on=[str(d) for d in depends],
                        source_path=str(source_path),
                    ))

        return ParserResult(
            parser_name=self.name,
            source_path=str(source_path),
            resources=resources,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Terraform Log Parser
# ---------------------------------------------------------------------------


class TerraformLogParser(BaseParser):
    """Parses Terraform apply/plan logs to extract resource operations."""

    name = "terraform_log"

    def supports(self, source_path: Path) -> bool:
        if source_path.suffix not in {".log", ".txt"}:
            return False
        try:
            text = source_path.read_text(encoding="utf-8")[:2000]
            return "Terraform" in text and ("Plan:" in text or "Apply" in text or "Refreshing state" in text)
        except Exception:
            return False

    def parse(self, source_path: Path) -> ParserResult:
        try:
            text = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ParserError(f"Could not read log file: {source_path}", cause=exc) from exc

        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []

        # Match patterns like: aws_instance.app: Creating... / aws_vpc.main: Refreshing state...
        resource_pattern = re.compile(
            r"([\w]+\.[\w\[\]\"]+):\s+(Creating|Modifying|Destroying|Refreshing state|Creation complete|Still creating)"
        )

        seen: set[str] = set()
        for match in resource_pattern.finditer(text):
            address = match.group(1)
            if address in seen:
                continue
            seen.add(address)

            parts = address.split(".", 1)
            resource_type = parts[0] if len(parts) > 1 else address
            resource_name = parts[1] if len(parts) > 1 else address

            provider = CloudProvider.UNKNOWN
            if resource_type.startswith("aws_"):
                provider = CloudProvider.AWS
            elif resource_type.startswith("google_"):
                provider = CloudProvider.GCP

            resources.append(ParsedResource(
                source_provider=provider,
                source_type=resource_type,
                source_identifier=address,
                name=resource_name,
                attributes={"log_action": match.group(2)},
                raw_depends_on=[],
                source_path=str(source_path),
            ))

        return ParserResult(
            parser_name=self.name,
            source_path=str(source_path),
            resources=resources,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Excel Inventory Parser
# ---------------------------------------------------------------------------


def _cell_to_str(value: Any) -> str:
    """Normalize a raw openpyxl cell value to str: None/merged cells -> '',
    datetimes -> ISO string, whole-number floats -> plain int string.
    """
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _first_sheet_with_data(wb: Any) -> tuple[Any, list[tuple[Any, ...]]]:
    """Some exports carry empty placeholder sheets before the real data —
    use the first sheet that actually has a non-empty row, not just wb.active.
    """
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if any(any(c not in (None, "") for c in row) for row in rows):
            return ws, rows
    return None, []


class ExcelInventoryParser(BaseParser):
    """Parses Excel (.xlsx) inventory files.

    Same alias/inference logic as CSVInventoryParser (see
    `column_detection.py`), plus Excel-specific quirks: a title row before
    the real header row, numeric/date cell values, and picking the first
    sheet that actually has data.
    """

    name = "excel_inventory"

    def supports(self, source_path: Path) -> bool:
        return source_path.suffix in {".xlsx", ".xls"}

    def parse(self, source_path: Path) -> ParserResult:
        try:
            import openpyxl
        except ImportError as exc:
            raise ParserError(
                "openpyxl is required for Excel parsing: pip install openpyxl",
                cause=exc,
            ) from exc

        try:
            wb = openpyxl.load_workbook(str(source_path), read_only=True, data_only=True)
            ws, raw_rows = _first_sheet_with_data(wb)
            wb.close()
        except Exception as exc:
            raise ParserError(f"Could not read Excel file: {source_path}", cause=exc) from exc

        if ws is None or not raw_rows:
            return ParserResult(parser_name=self.name, source_path=str(source_path))

        # Some exports put a title ("AWS Resource Inventory") in row 1 and
        # the real headers in row 2 — a title row has very few non-empty
        # cells relative to the sheet's actual width.
        header_row_idx = 0
        first_row = raw_rows[0]
        if len(raw_rows) > 1 and len(first_row) > 2:
            nonempty = sum(1 for c in first_row if c not in (None, ""))
            if nonempty <= 2:
                header_row_idx = 1

        header_row = raw_rows[header_row_idx]
        headers = [_cell_to_str(h) or f"col_{i}" for i, h in enumerate(header_row)]

        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []

        for row_num, row in enumerate(raw_rows[header_row_idx + 1 :], header_row_idx + 2):
            try:
                row_dict = {headers[i]: _cell_to_str(v) for i, v in enumerate(row) if i < len(headers)}
                resource = build_resource_from_row(row_dict, row_num, str(source_path))
                if resource is None:
                    continue  # blank row
                resources.append(resource)
            except Exception as exc:
                warnings.append(ParseWarning(message=f"Row {row_num}: {exc}"))

        return ParserResult(
            parser_name=self.name,
            source_path=str(source_path),
            resources=resources,
            warnings=warnings,
        )
