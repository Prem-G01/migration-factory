# API Reference

## Core

### Settings (`migration_factory.core.config`)

```python
from migration_factory.core.config import Settings, get_settings

settings = Settings()                    # reads env vars + .env
settings = get_settings()               # process-wide singleton
settings = get_settings(force_reload=True)  # re-read env in tests
```

| Env var | Type | Default | Description |
|---------|------|---------|-------------|
| `MF_ENVIRONMENT` | `dev\|staging\|prod` | `dev` | Runtime environment |
| `MF_SERVICE_NAME` | `str` | `migration-factory` | Service identifier for logs |
| `MF_DATA_DIR` | `Path` | `./data` | Working data directory |
| `MF_LOGGING__LEVEL` | `DEBUG\|INFO\|WARNING\|ERROR` | `INFO` | Log level |
| `MF_LOGGING__FORMAT` | `json\|console` | `json` | Log output format |
| `MF_PLUGINS__FAIL_FAST_ON_LOAD_ERROR` | `bool` | `False` | Abort on broken plugin |
| `MF_PARSING__MAX_INPUT_FILE_SIZE_MB` | `int` | `256` | Max input file size |
| `MF_PARSING__FAIL_ON_UNSUPPORTED_RESOURCE` | `bool` | `False` | Hard-fail on unmapped types |

### Logging (`migration_factory.core.logging`)

```python
from migration_factory.core.logging import configure_logging, get_logger, execution_context

configure_logging(settings)        # call once at startup
logger = get_logger(__name__)      # module-scoped logger

with execution_context() as trace_id:
    logger.info("run_started")     # trace_id auto-injected into every log line
```

### Exceptions (`migration_factory.core.exceptions`)

Every exception carries `error_code`, `context`, and `remediation`:

```python
from migration_factory.core.exceptions import ParserError

raise ParserError(
    "Could not read file",
    context={"path": "/tmp/bad.tfstate"},
    remediation="Verify the file exists and is readable.",
)
```

| Exception | error_code | Use case |
|-----------|-----------|----------|
| `MigrationFactoryError` | `MIGRATION_FACTORY_ERROR` | Base class |
| `ConfigurationError` | `CONFIGURATION_ERROR` | Invalid settings |
| `PluginError` | `PLUGIN_ERROR` | Plugin load failure |
| `ParserError` | `PARSER_ERROR` | Unreadable input |
| `UnsupportedResourceError` | `UNSUPPORTED_RESOURCE` | No parser/mapper |
| `MappingError` | `MAPPING_ERROR` | Normalization failure |
| `DependencyGraphError` | `DEPENDENCY_GRAPH_ERROR` | Cycles, dangling refs |
| `ValidationError` | `VALIDATION_ERROR` | Schema/content violation |
| `TranslationError` | `TRANSLATION_ERROR` | Translation failure |

### Container (`migration_factory.core.container`)

```python
from migration_factory.core.container import Container

container = Container()
container.register_singleton(MyInterface, lambda: MyImpl())
container.register_factory(MyInterface, MyImpl)
container.register_instance(MyInterface, my_instance)
instance = container.resolve(MyInterface)
```

---

## Domain

### Canonical Model (`migration_factory.domain.canonical_model`)

```python
from migration_factory.domain.canonical_model import CanonicalResource, CanonicalInfrastructureGraph

graph = CanonicalInfrastructureGraph()
graph.add_resource(resource)
order = graph.topological_order()    # deployment order
destroy = graph.destroy_order()      # reverse
dangling = graph.validate_references()
```

`CanonicalResource` fields: `id`, `canonical_type`, `source_provider`, `source_type`, `name`, `region`, `tags`, `owner`, `environment`, `criticality`, `application`, `cost_center`, `notes`, `depends_on`, `native_attributes`, `source_location`, `lifecycle_state`, `discovered_at`.

---

## Engines

### IngestionPipeline (`migration_factory.pipeline`)

```python
from migration_factory.pipeline import IngestionPipeline
pipeline = IngestionPipeline()
report = pipeline.run(Path("terraform.tfstate"))
# report.graph -> CanonicalInfrastructureGraph
```

### TranslationEngine (`migration_factory.translation.engine`)

```python
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
report = TranslationEngine(matrix=matrix).translate(graph)
```

### AssessmentEngine (`migration_factory.assessment.engine`)

```python
assessment = AssessmentEngine().assess(graph, translation)
# assessment.overall_complexity_score, .risk_level, .phases, .blockers
```

### PolicyEngine (`migration_factory.policy.engine`)

```python
report = PolicyEngine(parameters={"required_tags": ["Environment"]}).evaluate(graph)
# report.compliance_score, .by_framework("CIS"), .by_category()
```

### SecurityEngine (`migration_factory.security.engine`)

```python
report = SecurityEngine().analyze(graph)
# report.security_score, .iam_findings, .secret_findings, .firewall_findings
```

### ComplianceEngine (`migration_factory.compliance.engine`)

```python
report = ComplianceEngine().evaluate(graph)
# report.overall_compliance_score, .framework_results, .compliant_frameworks
```

### FinOpsEngine (`migration_factory.finops.engine`)

```python
report = FinOpsEngine(target_provider=CloudProvider.GCP).analyze(graph)
# report.cost_summary.monthly_savings, .break_even_months
```

### ValidationEngine (`migration_factory.validation.engine`)

```python
report = ValidationEngine().validate(graph)
# report.is_valid, .errors, .warnings
```

### TerraformGenerator (`migration_factory.terraform_gen.engine`)

```python
gen = TerraformGenerator(project_id="my-project", region="us-central1")
report = gen.generate(graph, translation)
gen.write(report, Path("./output"))
imports = gen.generate_import_blocks(graph, translation)
modules = gen.generate_module_structure(graph, translation)
```

### AIEngine (`migration_factory.ai.engine`)

```python
ai = AIEngine(api_key="sk-...")  # or reads ANTHROPIC_API_KEY env var
result = ai.explain_infrastructure(graph)
result = ai.analyze_migration_risks(graph, translation, assessment)
result = ai.suggest_optimizations(graph, translation, 500.0, 420.0)
result = ai.generate_documentation(graph, translation, assessment)
# result.content, .key_findings, .recommendations, .fallback
```

### KnowledgeGraphEngine (`migration_factory.knowledge_graph.engine`)

```python
report = KnowledgeGraphEngine().analyze(graph)
# report.typed_edges, .impact_analysis, .critical_resources, .application_groups
```

### RollbackPlanner (`migration_factory.rollback.engine`)

```python
plan = RollbackPlanner().plan(graph, translation)
# plan.rollback_steps, .estimated_duration_minutes, .risk_assessment
```

### MigrationPlanner (`migration_factory.planner.engine`)

```python
plan = MigrationPlanner().plan(graph, assessment, translation)
# plan.waves, .cutover_plan, .confidence, .maintenance_window
```

### DiscoveryEngine (`migration_factory.discovery.engine`)

```python
report = DiscoveryEngine().enrich(graph)  # auto-classify from tags
# report.resources_enriched, .unclassified_resources
```

### ReportingEngine (`migration_factory.reporting.engine`)

```python
report = ReportingEngine().generate(assessment=a, security=s, compliance=c, finops=f)
markdown = report.to_markdown()
html = ReportingEngine().to_html(report)
```

### EventBus (`migration_factory.events.engine`)

```python
bus = EventBus()
bus.subscribe(EventType.PIPELINE_COMPLETED, my_handler)
bus.publish(Event(event_type=EventType.PIPELINE_STARTED, source="cli"))
```

---

## CLI

```bash
migration-factory ingest <file>              # parse + normalize
migration-factory ingest <file> --output report.json
```
