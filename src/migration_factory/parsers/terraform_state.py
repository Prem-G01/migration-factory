"""Terraform State Parser.

Parses Terraform state files (format_version "4", the format used by
Terraform >= 0.13, which covers the overwhelming majority of estates a
migration project will encounter). State is preferred over `.tf` HCL source
as the first parser because it reflects *actual deployed reality*, including
values HCL never expresses directly (provider-computed defaults, resolved
`for_each`/`count` instances) — exactly what a migration needs to be
accurate against.

Design notes:
  * `data` resources are intentionally skipped (not infrastructure to
    migrate) and counted in the returned report rather than silently dropped.
  * Multi-instance resources (`count`/`for_each`) each become their own
    `ParsedResource` with a distinct `source_identifier`
    (`aws_instance.web[0]`, `aws_instance.web["primary"]`), matching
    Terraform's own addressing so later cross-referencing (plan/state diffs,
    generated `terraform import` blocks) lines up exactly.
  * A malformed *individual* resource block is recorded as a `ParseWarning`
    and skipped; only a structurally invalid file (bad JSON, unsupported
    `format_version`) raises `ParserError` and aborts the whole parse.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from migration_factory.core.exceptions import ParserError
from migration_factory.core.logging import get_logger
from migration_factory.domain.enums import CloudProvider
from migration_factory.parsers.base import BaseParser, ParsedResource, ParserResult, ParseWarning

logger = get_logger(__name__)

SUPPORTED_FORMAT_VERSIONS = {"4"}

_PROVIDER_MARKERS: dict[str, CloudProvider] = {
    "registry.terraform.io/hashicorp/aws": CloudProvider.AWS,
    "registry.terraform.io/hashicorp/google": CloudProvider.GCP,
    "registry.terraform.io/hashicorp/google-beta": CloudProvider.GCP,
    "registry.terraform.io/hashicorp/azurerm": CloudProvider.AZURE,
}


def _infer_provider(provider_config_key: str) -> CloudProvider:
    """Terraform state stores a provider config *key*, not the registry
    address directly, in modern versions; but the `provider_name` at the
    instance level (`registry.terraform.io/hashicorp/aws`) is authoritative
    and always present in format_version 4 — that's what callers pass here.
    """
    for marker, provider in _PROVIDER_MARKERS.items():
        if marker in provider_config_key:
            return provider
    return CloudProvider.UNKNOWN


class TerraformStateParser(BaseParser):
    name = "terraform_state"

    def supports(self, source_path: Path) -> bool:
        if source_path.suffix not in {".tfstate", ".json"}:
            return False
        try:
            with source_path.open(encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        return isinstance(payload, dict) and "format_version" in payload and "resources" in payload

    def parse(self, source_path: Path) -> ParserResult:
        try:
            with source_path.open(encoding="utf-8") as f:
                state: dict[str, Any] = json.load(f)
        except OSError as exc:
            raise ParserError(
                f"Could not read Terraform state file: {source_path}",
                context={"source_path": str(source_path)},
                remediation="Verify the file exists and is readable.",
                cause=exc,
            ) from exc
        except json.JSONDecodeError as exc:
            raise ParserError(
                f"Terraform state file is not valid JSON: {source_path}",
                context={"source_path": str(source_path), "json_error": str(exc)},
                remediation="Re-export the state with `terraform show -json` or "
                "verify the file was not truncated during transfer.",
                cause=exc,
            ) from exc

        format_version = str(state.get("format_version", ""))
        if format_version not in SUPPORTED_FORMAT_VERSIONS:
            raise ParserError(
                f"Unsupported Terraform state format_version: {format_version!r}",
                context={
                    "source_path": str(source_path),
                    "format_version": format_version,
                    "supported": sorted(SUPPORTED_FORMAT_VERSIONS),
                },
                remediation="Upgrade/downgrade Terraform to produce a supported state "
                "format, or run `terraform state replace-provider`/state migration first.",
            )

        resources: list[ParsedResource] = []
        warnings: list[ParseWarning] = []
        skipped_data_sources = 0

        for resource_block in state.get("resources", []):
            mode = resource_block.get("mode")
            if mode == "data":
                skipped_data_sources += 1
                continue
            if mode != "managed":
                warnings.append(
                    ParseWarning(
                        message=f"Skipping resource block with unrecognized mode {mode!r}",
                    )
                )
                continue

            resource_type = resource_block.get("type", "")
            resource_name = resource_block.get("name", "")
            module_path = resource_block.get("module")  # e.g. "module.network"
            address_prefix = f"{module_path}." if module_path else ""

            for instance in resource_block.get("instances", []):
                try:
                    resources.append(
                        self._build_parsed_resource(
                            resource_type=resource_type,
                            resource_name=resource_name,
                            address_prefix=address_prefix,
                            instance=instance,
                            source_path=str(source_path),
                        )
                    )
                except (KeyError, TypeError) as exc:
                    identifier = f"{address_prefix}{resource_type}.{resource_name}"
                    warnings.append(
                        ParseWarning(
                            source_identifier=identifier,
                            message=f"Malformed resource instance, skipped: {exc}",
                            remediation="Inspect this resource block manually; state "
                            "may be from an incompatible provider schema version.",
                        )
                    )
                    logger.warning(
                        "terraform_state_resource_skipped",
                        resource_identifier=identifier,
                        error=str(exc),
                    )

        logger.info(
            "terraform_state_parsed",
            source_path=str(source_path),
            resource_count=len(resources),
            warning_count=len(warnings),
            skipped_data_sources=skipped_data_sources,
        )

        return ParserResult(
            parser_name=self.name,
            source_path=str(source_path),
            resources=resources,
            warnings=warnings,
        )

    @staticmethod
    def _build_parsed_resource(
        *,
        resource_type: str,
        resource_name: str,
        address_prefix: str,
        instance: dict[str, Any],
        source_path: str,
    ) -> ParsedResource:
        attributes: dict[str, Any] = instance["attributes"]
        index_key = instance.get("index_key")

        if index_key is None:
            address = f"{address_prefix}{resource_type}.{resource_name}"
        elif isinstance(index_key, str):
            address = f'{address_prefix}{resource_type}.{resource_name}["{index_key}"]'
        else:
            address = f"{address_prefix}{resource_type}.{resource_name}[{index_key}]"

        provider_name = instance.get("provider_name", "") or ""
        provider = _infer_provider(provider_name) if provider_name else _infer_provider(
            resource_type.split("_", maxsplit=1)[0]
        )

        raw_depends_on = list(instance.get("dependencies") or [])

        resource_id = attributes.get("id") or attributes.get("arn") or attributes.get("name")
        display_name = str(resource_id) if resource_id is not None else address

        return ParsedResource(
            source_provider=provider,
            source_type=resource_type,
            source_identifier=address,
            name=display_name,
            attributes=attributes,
            raw_depends_on=raw_depends_on,
            source_path=source_path,
        )
