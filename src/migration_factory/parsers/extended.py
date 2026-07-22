"""Terraform HCL Parser, Terraform Log Parser, and Excel Inventory Parser.

Completes the parser suite: every input format in the original spec now has
a working parser registered via entry points.
"""

from __future__ import annotations

import re
from pathlib import Path

from migration_factory.core.exceptions import ParserError
from migration_factory.core.logging import get_logger
from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.base import BaseParser, ParsedResource, ParserResult, ParseWarning

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


class ExcelInventoryParser(BaseParser):
    """Parses Excel (.xlsx) inventory files. Expects columns: type, name, id, provider."""

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
            ws = wb.active
        except Exception as exc:
            raise ParserError(f"Could not read Excel file: {source_path}", cause=exc) from exc

        if ws is None:
            return ParserResult(parser_name=self.name, source_path=str(source_path))

        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return ParserResult(parser_name=self.name, source_path=str(source_path))

        # First row is headers
        headers = [str(h).strip().lower() if h else f"col_{i}" for i, h in enumerate(rows[0])]

        for row_num, row in enumerate(rows[1:], 2):
            try:
                row_dict = {headers[i]: str(v).strip() if v is not None else "" for i, v in enumerate(row) if i < len(headers)}

                resource_type = row_dict.get("type", "unknown")
                name = row_dict.get("name", "unnamed")
                rid = row_dict.get("id", name)
                provider_str = row_dict.get("provider", "aws").lower()

                provider = CloudProvider.UNKNOWN
                if provider_str in {e.value for e in CloudProvider}:
                    provider = CloudProvider(provider_str)

                attrs = {k: v for k, v in row_dict.items() if k not in {"type", "name", "id", "provider", "depends_on"}}
                depends = [d.strip() for d in row_dict.get("depends_on", "").split(",") if d.strip()]

                resources.append(ParsedResource(
                    source_provider=provider,
                    source_type=resource_type,
                    source_identifier=rid,
                    name=name,
                    attributes=attrs,
                    raw_depends_on=depends,
                    source_path=str(source_path),
                ))
            except Exception as exc:
                warnings.append(ParseWarning(message=f"Row {row_num}: {exc}"))

        wb.close()
        return ParserResult(
            parser_name=self.name,
            source_path=str(source_path),
            resources=resources,
            warnings=warnings,
        )
