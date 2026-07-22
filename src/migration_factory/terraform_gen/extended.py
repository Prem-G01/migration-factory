"""Terraform Generation extensions: environment-specific tfvars, test
generation, and formatter stub.
"""

from __future__ import annotations

from dataclasses import dataclass

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.terraform_gen.engine import GeneratedFile, _tf_name
from migration_factory.translation.models import SupportStatus, TranslationReport

logger = get_logger(__name__)


@dataclass(slots=True)
class TerraformEnvironmentGenerator:
    """Generates per-environment tfvars (dev, staging, prod)."""

    environments: list[str] = ("dev", "staging", "prod")  # type: ignore[assignment]

    def generate(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
        project_prefix: str = "myproject",
    ) -> list[GeneratedFile]:
        translation_index = {tr.resource_id: tr for tr in translation.results}
        files: list[GeneratedFile] = []

        for env in self.environments:
            lines = [f'# {env} environment variables', f'project_id = "{project_prefix}-{env}"', 'region = "us-central1"', '']

            for resource in graph.resources.values():
                tr = translation_index.get(resource.id)
                if tr is None or tr.status is SupportStatus.UNSUPPORTED:
                    continue
                name = _tf_name(resource)
                lines.append(f'{name}_name = "{name}-{env}"')

            files.append(GeneratedFile(
                filename=f"environments/{env}.tfvars",
                content="\n".join(lines) + "\n",
                description=f"Variable overrides for {env} environment",
            ))

        files.append(GeneratedFile(
            filename="environments/README.md",
            content="# Environments\n\nApply with: `terraform apply -var-file=environments/dev.tfvars`\n",
            description="Environment usage instructions",
        ))

        return files


@dataclass(slots=True)
class TerraformTestGenerator:
    """Generates basic Terraform test files (terraform test framework)."""

    def generate(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
    ) -> list[GeneratedFile]:
        translation_index = {tr.resource_id: tr for tr in translation.results}
        test_blocks: list[str] = []

        test_blocks.append('# Auto-generated Terraform tests')
        test_blocks.append('# Run with: terraform test\n')

        # Validation test
        test_blocks.append('run "validate_plan" {')
        test_blocks.append('  command = plan\n')
        test_blocks.append('  assert {')
        test_blocks.append('    condition     = true')
        test_blocks.append('    error_message = "Plan should succeed without errors"')
        test_blocks.append('  }')
        test_blocks.append('}\n')

        # Per-resource existence tests
        for resource in graph.resources.values():
            tr = translation_index.get(resource.id)
            if tr is None or tr.status is SupportStatus.UNSUPPORTED:
                continue
            if not tr.target_terraform_types:
                continue

            name = _tf_name(resource)
            tf_type = tr.target_terraform_types[0]
            test_blocks.append(f'run "test_{name}_created" {{')
            test_blocks.append('  command = plan\n')
            test_blocks.append('  assert {')
            test_blocks.append(f'    condition     = {tf_type}.{name}.id != ""')
            test_blocks.append(f'    error_message = "{name} should be created"')
            test_blocks.append('  }')
            test_blocks.append('}\n')

        files = [
            GeneratedFile(
                filename="tests/main.tftest.hcl",
                content="\n".join(test_blocks),
                description="Terraform test file for plan validation",
            ),
        ]

        return files


def format_terraform(content: str) -> str:
    """Basic Terraform HCL formatter.

    Normalizes indentation and spacing. For production use, shell out to
    `terraform fmt` — this is a best-effort formatter for environments
    where the terraform binary isn't available.
    """
    lines = content.split("\n")
    formatted: list[str] = []
    indent = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            formatted.append("")
            continue

        # Decrease indent for closing braces
        if stripped.startswith("}") or stripped.startswith("]"):
            indent = max(0, indent - 1)

        formatted.append("  " * indent + stripped)

        # Increase indent for opening braces
        if stripped.endswith("{") or stripped.endswith("["):
            indent += 1

    return "\n".join(formatted)
