# Configuration Reference

All settings are configured via environment variables with the `MF_` prefix. Nested settings use `__` as the delimiter. A `.env` file in the project root is also read automatically.

## Core settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MF_ENVIRONMENT` | `dev\|staging\|prod` | `dev` | Runtime environment. Controls `is_production` flag. |
| `MF_SERVICE_NAME` | `string` | `migration-factory` | Service identifier for structured logs. |
| `MF_DATA_DIR` | `path` | `./data` | Working data directory for intermediate files. |

## Logging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MF_LOGGING__LEVEL` | `DEBUG\|INFO\|WARNING\|ERROR\|CRITICAL` | `INFO` | Python logging level. |
| `MF_LOGGING__FORMAT` | `json\|console` | `json` | `json` for production (structured), `console` for local dev (human-readable). |
| `MF_LOGGING__INCLUDE_TRACE_ID` | `bool` | `true` | Include `trace_id` and `execution_id` in every log line. |

## Plugin management

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MF_PLUGINS__PARSER_ENTRYPOINT_GROUP` | `string` | `migration_factory.parsers` | Entry-point group for parser plugins. |
| `MF_PLUGINS__MAPPER_ENTRYPOINT_GROUP` | `string` | `migration_factory.mappers` | Entry-point group for mapper plugins. |
| `MF_PLUGINS__FAIL_FAST_ON_LOAD_ERROR` | `bool` | `false` | If `true`, a single broken plugin aborts startup. If `false`, broken plugins are logged and skipped. |

## Parsing

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MF_PARSING__MAX_INPUT_FILE_SIZE_MB` | `int` (1-4096) | `256` | Maximum input file size in MB. |
| `MF_PARSING__FAIL_ON_UNSUPPORTED_RESOURCE` | `bool` | `false` | If `true`, encountering a resource type with no registered mapper is a hard failure. If `false` (recommended), it is recorded as a warning and the run continues. |

## AI Engine

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ANTHROPIC_API_KEY` | `string` | (none) | Anthropic API key for AI-powered analysis. If unset, all AI methods return deterministic fallbacks. |

## Policy Engine parameters

Policy checks accept parameters passed to `PolicyEngine(parameters={...})`:

| Parameter | Type | Used by | Description |
|-----------|------|---------|-------------|
| `required_prefix` | `string` | `naming.resource_prefix` | Required name prefix for all resources. |
| `required_tags` | `list[str]` | `tags.required` | Tag keys that must exist on every resource. |
| `allowed_tag_values` | `dict[str, list[str]]` | `tags.values` | Allowed values per tag key. |
| `allowed_regions` | `list[str]` | `region.allowed` | Regions where resources may be deployed. |
| `required_org_fields` | `list[str]` | `org.hierarchy` | Required organization metadata fields. |

## Terraform Generator

| Constructor arg | Type | Default | Description |
|----------------|------|---------|-------------|
| `target_provider` | `CloudProvider` | `GCP` | Target cloud for Terraform generation. |
| `project_id` | `string` | `your-gcp-project-id` | GCP project ID for provider config. |
| `region` | `string` | `us-central1` | Default GCP region. |

## FinOps Engine

| Constructor arg | Type | Default | Description |
|----------------|------|---------|-------------|
| `target_provider` | `CloudProvider` | `GCP` | Target cloud for cost comparison. |

## Compliance Engine

| Constructor arg | Type | Default | Description |
|----------------|------|---------|-------------|
| `frameworks` | `list[str]` | `["CIS","NIST","SOC2","PCI_DSS","ISO27001","HIPAA"]` | Frameworks to evaluate. |
| `compliance_threshold` | `float` | `80.0` | Score threshold for "compliant" classification. |

## Example .env file

```bash
MF_ENVIRONMENT=prod
MF_LOGGING__LEVEL=INFO
MF_LOGGING__FORMAT=json
MF_PARSING__FAIL_ON_UNSUPPORTED_RESOURCE=false
ANTHROPIC_API_KEY=sk-ant-...
```
