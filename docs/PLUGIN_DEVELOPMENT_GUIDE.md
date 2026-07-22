# Plugin Development Guide

## Overview

The Migration Factory is designed so that external teams can extend it without modifying core code. Parsers, mappers, and policy checks are all plugin points — you implement an interface, register an entry point, and the platform discovers your plugin automatically.

## Plugin types

| Plugin type | Interface | Entry-point group | Purpose |
|------------|-----------|-------------------|---------|
| Parser | `BaseParser` | `migration_factory.parsers` | Convert a new input format to `ParsedResource` |
| Mapper | `BaseMapper` | `migration_factory.mappers` | Normalize a provider's resources to `CanonicalResource` |
| Policy check | function | `CHECK_IMPLEMENTATIONS` dict | Evaluate a rule against a resource |

## Creating a parser plugin

### 1. Implement `BaseParser`

```python
# my_parser_package/arm_parser.py
from pathlib import Path
from migration_factory.parsers.base import BaseParser, ParsedResource, ParserResult
from migration_factory.domain.enums import CloudProvider

class ARMTemplateParser(BaseParser):
    name = "arm_template"

    def supports(self, source_path: Path) -> bool:
        """Return True if this parser can handle this file.
        Must be cheap, side-effect-free, and never raise."""
        if source_path.suffix != ".json":
            return False
        try:
            import json
            data = json.loads(source_path.read_text())
            return "$schema" in data and "resources" in data
        except Exception:
            return False

    def parse(self, source_path: Path) -> ParserResult:
        """Parse the file into ParsedResource records.
        Raise ParserError for unrecoverable issues.
        Record per-resource issues as ParseWarning (don't abort)."""
        import json
        data = json.loads(source_path.read_text())

        resources = []
        for arm_resource in data.get("resources", []):
            resources.append(ParsedResource(
                source_provider=CloudProvider.AZURE,
                source_type=arm_resource["type"],
                source_identifier=arm_resource.get("name", ""),
                name=arm_resource.get("name", "unnamed"),
                attributes=arm_resource.get("properties", {}),
                raw_depends_on=arm_resource.get("dependsOn", []),
                source_path=str(source_path),
            ))

        return ParserResult(
            parser_name=self.name,
            source_path=str(source_path),
            resources=resources,
        )
```

### 2. Register the entry point

In your package's `pyproject.toml`:

```toml
[project.entry-points."migration_factory.parsers"]
arm_template = "my_parser_package.arm_parser:ARMTemplateParser"
```

### 3. Install and verify

```bash
pip install -e .
# The parser is now auto-discovered — test it:
migration-factory ingest my_template.json
```

## Creating a mapper plugin

Same pattern — implement `BaseMapper`:

```python
from migration_factory.mappers.base import BaseMapper
from migration_factory.domain.canonical_model import CanonicalResource, SourceLocation
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider

class AzureToCanonicalMapper(BaseMapper):
    name = "azure_to_canonical"

    def supports(self, source_type: str) -> bool:
        return "Microsoft." in source_type

    def map(self, parsed: ParsedResource) -> CanonicalResource:
        # Map Azure resource types to canonical types
        ...
```

Register under `migration_factory.mappers`.

## Creating a policy check

Policy checks are simpler — just a function and a dict registration:

```python
from migration_factory.policy.engine import CHECK_IMPLEMENTATIONS, _finding
from migration_factory.policy.models import PolicyDefinition, PolicyStatus

def check_custom_naming(resource, graph, policy, parameters):
    pattern = parameters.get("naming_pattern", "")
    if not pattern:
        return _finding(policy, resource, PolicyStatus.SKIP, "No pattern configured")
    import re
    if re.match(pattern, resource.name):
        return _finding(policy, resource, PolicyStatus.PASS, "Name matches pattern")
    return _finding(policy, resource, PolicyStatus.FAIL, f"Name does not match {pattern}")

# Register
CHECK_IMPLEMENTATIONS["naming.custom_pattern"] = check_custom_naming
```

## Testing your plugin

```python
import pytest
from pathlib import Path
from my_parser_package.arm_parser import ARMTemplateParser

def test_supports_arm_template(tmp_path):
    template = {"$schema": "...", "resources": []}
    path = tmp_path / "template.json"
    path.write_text(json.dumps(template))
    assert ARMTemplateParser().supports(path) is True

def test_parses_arm_resources(tmp_path):
    template = {"$schema": "...", "resources": [
        {"type": "Microsoft.Compute/virtualMachines", "name": "vm1", "properties": {}}
    ]}
    path = tmp_path / "template.json"
    path.write_text(json.dumps(template))
    result = ARMTemplateParser().parse(path)
    assert result.resource_count == 1
```

## Publishing

Package your plugin as a standard Python wheel. Users install it alongside the platform:

```bash
pip install migration-factory my-arm-parser-plugin
```

The entry-point registration in your `pyproject.toml` ensures the platform discovers your parser/mapper at startup — no configuration needed by the end user.
