"""AI Intelligence Engine.

Provides AI-powered analysis ON TOP of deterministic engine outputs:
infrastructure explanation, migration risk analysis, optimization
suggestions, root cause analysis, and documentation generation.

Design rules:
1. **AI advises, rules decide.** The AI layer NEVER produces translation
   decisions, cost estimates, or compliance verdicts — those come from the
   deterministic engines. AI explains, summarizes, and suggests.
2. **Every AI call is auditable.** The prompt sent and response received are
   both logged with trace_id, so a human can review what the AI was shown
   and what it said.
3. **Graceful degradation.** If the AI API is unavailable, every method
   returns a structured fallback — the platform never fails because AI is
   down.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.assessment.models import MigrationAssessment
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.translation.models import TranslationReport

logger = get_logger(__name__)


class AIAnalysisType(StrEnum):
    INFRASTRUCTURE_EXPLANATION = "infrastructure_explanation"
    MIGRATION_RISK_ANALYSIS = "migration_risk_analysis"
    OPTIMIZATION_SUGGESTIONS = "optimization_suggestions"
    MIGRATION_PLAN_NARRATIVE = "migration_plan_narrative"
    ROOT_CAUSE_ANALYSIS = "root_cause_analysis"
    ARCHITECTURE_SUMMARY = "architecture_summary"
    DOCUMENTATION = "documentation"


class AIAnalysisResult(BaseModel):
    """Structured result from an AI analysis call."""

    model_config = ConfigDict(extra="forbid")

    analysis_type: AIAnalysisType
    content: str
    confidence: str = Field(default="medium", description="low, medium, high")
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    prompt_used: str = Field(default="", description="Audit trail: the prompt sent to the AI")
    model_used: str = ""
    fallback: bool = Field(default=False, description="True if AI was unavailable and this is a rule-based fallback")


class PromptTemplate(BaseModel):
    """A versioned, reusable prompt template."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    template: str
    analysis_type: AIAnalysisType
    version: str = "1.0"


# ---------------------------------------------------------------------------
# Prompt library — versioned, auditable, replaceable
# ---------------------------------------------------------------------------

PROMPT_TEMPLATES: dict[AIAnalysisType, PromptTemplate] = {
    AIAnalysisType.INFRASTRUCTURE_EXPLANATION: PromptTemplate(
        name="infrastructure_explanation",
        analysis_type=AIAnalysisType.INFRASTRUCTURE_EXPLANATION,
        template="""You are an expert cloud infrastructure analyst. Analyze this infrastructure estate and provide a clear, executive-level explanation.

Infrastructure Summary:
- Total resources: {resource_count}
- Resource types: {resource_types}
- Source provider: {source_provider}
- Regions: {regions}
- Dependencies: {dependency_count} edges

Resource Details:
{resource_details}

Provide:
1. A concise explanation of what this infrastructure does (2-3 sentences)
2. The architecture pattern being used (e.g., three-tier, microservices, serverless)
3. Key observations about the design
4. Potential concerns or anti-patterns

Respond in JSON format with keys: explanation, architecture_pattern, observations (list), concerns (list).""",
    ),
    AIAnalysisType.MIGRATION_RISK_ANALYSIS: PromptTemplate(
        name="migration_risk_analysis",
        analysis_type=AIAnalysisType.MIGRATION_RISK_ANALYSIS,
        template="""You are a cloud migration risk analyst. Analyze this migration plan and identify risks.

Migration: {source_provider} → {target_provider}
Overall complexity score: {complexity_score}/100
Risk level: {risk_level}
Total resources: {resource_count}
Blockers: {blocker_count}

Translation Summary:
{translation_summary}

Assessment Summary:
{assessment_summary}

Blockers:
{blockers}

Provide a risk analysis including:
1. Top 3 risks with severity (critical/high/medium/low) and mitigation strategy
2. Resources that need the most attention
3. Recommended migration sequence adjustments
4. Go/no-go recommendation with reasoning

Respond in JSON format with keys: risks (list of {{risk, severity, mitigation}}), attention_resources (list), sequence_adjustments (list), recommendation (string).""",
    ),
    AIAnalysisType.OPTIMIZATION_SUGGESTIONS: PromptTemplate(
        name="optimization_suggestions",
        analysis_type=AIAnalysisType.OPTIMIZATION_SUGGESTIONS,
        template="""You are a cloud optimization expert. Analyze this infrastructure and suggest improvements for the target cloud.

Source: {source_provider} → Target: {target_provider}
Current monthly cost: ${source_cost}/month
Projected target cost: ${target_cost}/month

Resources:
{resource_details}

Provide optimization suggestions:
1. Cost optimization opportunities (specific to {target_provider})
2. Performance improvements possible during migration
3. Security hardening recommendations
4. Modernization opportunities (e.g., containerize, go serverless)

Respond in JSON format with keys: cost_optimizations (list), performance_improvements (list), security_recommendations (list), modernization_opportunities (list).""",
    ),
    AIAnalysisType.ARCHITECTURE_SUMMARY: PromptTemplate(
        name="architecture_summary",
        analysis_type=AIAnalysisType.ARCHITECTURE_SUMMARY,
        template="""You are a cloud architect. Generate a concise architecture summary for this infrastructure.

Resources ({resource_count} total):
{resource_details}

Dependencies:
{dependency_details}

Generate:
1. Architecture overview (3-4 sentences)
2. Component inventory by tier (networking, compute, data, security)
3. Data flow description
4. High availability assessment

Respond in JSON format with keys: overview, tiers (dict), data_flow, ha_assessment.""",
    ),
    AIAnalysisType.DOCUMENTATION: PromptTemplate(
        name="documentation",
        analysis_type=AIAnalysisType.DOCUMENTATION,
        template="""You are a technical writer specializing in cloud infrastructure documentation. Generate migration documentation.

Migration: {source_provider} → {target_provider}
Resources: {resource_count}
Phases: {phase_count}

Migration Plan:
{migration_plan}

Generate a migration runbook section including:
1. Pre-migration checklist
2. Step-by-step migration procedure for each phase
3. Validation steps after each phase
4. Rollback procedure
5. Post-migration verification

Write in clear, actionable Markdown format.""",
    ),
}


@dataclass(slots=True)
class AIEngine:
    """AI Intelligence Engine.

    Calls the Anthropic API for analysis when available; falls back to
    deterministic summaries when the API is unavailable or unconfigured.
    """

    api_key: str | None = field(default=None)
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 2000
    _initialized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self._initialized = self.api_key is not None

    @property
    def is_available(self) -> bool:
        return self._initialized

    def explain_infrastructure(
        self, graph: CanonicalInfrastructureGraph
    ) -> AIAnalysisResult:
        """Generate a human-readable explanation of what this infrastructure does."""
        context = self._build_graph_context(graph)
        prompt = PROMPT_TEMPLATES[AIAnalysisType.INFRASTRUCTURE_EXPLANATION].template.format(**context)

        if not self.is_available:
            return self._fallback_infrastructure_explanation(graph)

        return self._call_ai(prompt, AIAnalysisType.INFRASTRUCTURE_EXPLANATION)

    def analyze_migration_risks(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
        assessment: MigrationAssessment,
    ) -> AIAnalysisResult:
        """AI-powered migration risk analysis."""
        context = {
            "source_provider": translation.source_provider.value,
            "target_provider": translation.target_provider.value,
            "complexity_score": assessment.overall_complexity_score,
            "risk_level": assessment.risk_level.value,
            "resource_count": len(graph.resources),
            "blocker_count": len(assessment.blockers),
            "translation_summary": json.dumps(translation.summary, indent=2),
            "assessment_summary": "\n".join(
                f"- {a.resource_name}: score={a.complexity_score}, strategy={a.strategy.value}"
                for a in assessment.resource_assessments[:20]
            ),
            "blockers": "\n".join(f"- {b}" for b in assessment.blockers) or "None",
        }
        prompt = PROMPT_TEMPLATES[AIAnalysisType.MIGRATION_RISK_ANALYSIS].template.format(**context)

        if not self.is_available:
            return self._fallback_risk_analysis(assessment)

        return self._call_ai(prompt, AIAnalysisType.MIGRATION_RISK_ANALYSIS)

    def suggest_optimizations(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
        source_cost: float,
        target_cost: float,
    ) -> AIAnalysisResult:
        """AI-powered optimization suggestions for the target architecture."""
        context = {
            "source_provider": translation.source_provider.value,
            "target_provider": translation.target_provider.value,
            "source_cost": f"{source_cost:.0f}",
            "target_cost": f"{target_cost:.0f}",
            "resource_details": "\n".join(
                f"- {r.name} ({r.canonical_type.value}): {r.source_type}"
                for r in list(graph.resources.values())[:30]
            ),
        }
        prompt = PROMPT_TEMPLATES[AIAnalysisType.OPTIMIZATION_SUGGESTIONS].template.format(**context)

        if not self.is_available:
            return self._fallback_optimizations(graph, translation)

        return self._call_ai(prompt, AIAnalysisType.OPTIMIZATION_SUGGESTIONS)

    def generate_architecture_summary(
        self, graph: CanonicalInfrastructureGraph
    ) -> AIAnalysisResult:
        """Generate an architecture summary document."""
        context = self._build_graph_context(graph)
        context["dependency_details"] = "\n".join(
            f"- {r.id} depends on: {', '.join(r.depends_on) or 'none'}"
            for r in list(graph.resources.values())[:30]
        )
        prompt = PROMPT_TEMPLATES[AIAnalysisType.ARCHITECTURE_SUMMARY].template.format(**context)

        if not self.is_available:
            return self._fallback_architecture_summary(graph)

        return self._call_ai(prompt, AIAnalysisType.ARCHITECTURE_SUMMARY)

    def generate_documentation(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport,
        assessment: MigrationAssessment,
    ) -> AIAnalysisResult:
        """Generate migration runbook documentation."""
        context = {
            "source_provider": translation.source_provider.value,
            "target_provider": translation.target_provider.value,
            "resource_count": len(graph.resources),
            "phase_count": len(assessment.phases),
            "migration_plan": "\n".join(
                f"Phase {p.phase_number} ({p.name}): {len(p.resource_ids)} resources"
                for p in assessment.phases
            ),
        }
        prompt = PROMPT_TEMPLATES[AIAnalysisType.DOCUMENTATION].template.format(**context)

        if not self.is_available:
            return self._fallback_documentation(assessment, translation)

        return self._call_ai(prompt, AIAnalysisType.DOCUMENTATION)

    # ---------------------------------------------------------------------------
    # AI API call
    # ---------------------------------------------------------------------------

    def _call_ai(self, prompt: str, analysis_type: AIAnalysisType) -> AIAnalysisResult:
        """Call Anthropic API. Isolated here for testability and audit trail."""
        try:
            import httpx

            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key or "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")

            # Try to parse as JSON for structured results
            key_findings: list[str] = []
            recommendations: list[str] = []
            risks: list[str] = []

            try:
                parsed = json.loads(content.strip().removeprefix("```json").removesuffix("```").strip())
                if isinstance(parsed, dict):
                    key_findings = list(parsed.get("observations", parsed.get("key_findings", [])) or [])
                    recommendations = list(parsed.get("recommendations", parsed.get("cost_optimizations", [])) or [])
                    risks = [
                        f"[{r.get('severity', 'medium')}] {r.get('risk', r)}"
                        for r in parsed.get("risks", [])
                        if isinstance(r, dict)
                    ]
                    # Flatten content for display
                    content = json.dumps(parsed, indent=2)
            except (json.JSONDecodeError, AttributeError):
                pass

            logger.info("ai_call_completed", analysis_type=analysis_type.value, model=self.model)

            return AIAnalysisResult(
                analysis_type=analysis_type,
                content=content,
                confidence="high",
                key_findings=key_findings,
                recommendations=recommendations,
                risks=risks,
                prompt_used=prompt[:500] + "..." if len(prompt) > 500 else prompt,
                model_used=self.model,
            )

        except Exception as exc:
            logger.warning("ai_call_failed", analysis_type=analysis_type.value, error=str(exc))
            # Fall back to deterministic analysis
            return AIAnalysisResult(
                analysis_type=analysis_type,
                content=f"AI analysis unavailable: {exc}. Using deterministic fallback.",
                fallback=True,
                prompt_used=prompt[:200] + "...",
            )

    # ---------------------------------------------------------------------------
    # Deterministic fallbacks — platform works without AI
    # ---------------------------------------------------------------------------

    @staticmethod
    def _build_graph_context(graph: CanonicalInfrastructureGraph) -> dict[str, Any]:
        resources = list(graph.resources.values())
        types = sorted({r.canonical_type.value for r in resources})
        regions = sorted({r.region for r in resources if r.region})
        providers = sorted({r.source_provider.value for r in resources})
        dep_count = sum(len(r.depends_on) for r in resources)

        return {
            "resource_count": len(resources),
            "resource_types": ", ".join(types),
            "source_provider": providers[0] if providers else "unknown",
            "regions": ", ".join(regions) or "not specified",
            "dependency_count": dep_count,
            "resource_details": "\n".join(
                f"- {r.name} ({r.canonical_type.value}) in {r.region or 'unspecified'}"
                for r in resources[:30]
            ),
        }

    @staticmethod
    def _fallback_infrastructure_explanation(graph: CanonicalInfrastructureGraph) -> AIAnalysisResult:
        resources = list(graph.resources.values())
        types = sorted({r.canonical_type.value for r in resources})
        type_counts: dict[str, int] = {}
        for r in resources:
            category = r.canonical_type.value.split(".")[0]
            type_counts[category] = type_counts.get(category, 0) + 1

        explanation_parts = [f"Infrastructure estate with {len(resources)} resources across {len(types)} types."]
        for category, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            explanation_parts.append(f"{category}: {count} resources")

        return AIAnalysisResult(
            analysis_type=AIAnalysisType.INFRASTRUCTURE_EXPLANATION,
            content="\n".join(explanation_parts),
            confidence="medium",
            key_findings=[f"{len(types)} resource types detected", f"{len(resources)} total resources"],
            fallback=True,
        )

    @staticmethod
    def _fallback_risk_analysis(assessment: MigrationAssessment) -> AIAnalysisResult:
        risks = []
        if assessment.risk_level.value in ("high",):
            risks.append("High overall risk — multiple resources require manual migration")
        for a in assessment.resource_assessments:
            if a.strategy.value == "manual":
                risks.append(f"{a.resource_name}: requires manual migration (score: {a.complexity_score})")

        return AIAnalysisResult(
            analysis_type=AIAnalysisType.MIGRATION_RISK_ANALYSIS,
            content=f"Risk level: {assessment.risk_level.value}. {len(assessment.blockers)} blockers identified.",
            confidence="medium",
            key_findings=[f"Overall score: {assessment.overall_complexity_score}/100"],
            risks=risks[:10],
            recommendations=[b for b in assessment.blockers[:5]],
            fallback=True,
        )

    @staticmethod
    def _fallback_optimizations(graph: CanonicalInfrastructureGraph, translation: TranslationReport) -> AIAnalysisResult:
        suggestions = []
        for tr in translation.results:
            if tr.required_changes:
                suggestions.append(f"{tr.resource_name}: {tr.required_changes[0]}")

        return AIAnalysisResult(
            analysis_type=AIAnalysisType.OPTIMIZATION_SUGGESTIONS,
            content="Optimization analysis based on translation rules.",
            confidence="medium",
            recommendations=suggestions[:10],
            fallback=True,
        )

    @staticmethod
    def _fallback_architecture_summary(graph: CanonicalInfrastructureGraph) -> AIAnalysisResult:
        resources = list(graph.resources.values())
        tiers: dict[str, list[str]] = {}
        for r in resources:
            tier = r.canonical_type.value.split(".")[0]
            tiers.setdefault(tier, []).append(r.name)

        summary_parts = [f"Architecture with {len(resources)} resources across {len(tiers)} tiers:"]
        for tier, names in sorted(tiers.items()):
            summary_parts.append(f"  {tier}: {', '.join(names[:5])}")

        return AIAnalysisResult(
            analysis_type=AIAnalysisType.ARCHITECTURE_SUMMARY,
            content="\n".join(summary_parts),
            confidence="medium",
            key_findings=[f"{len(tiers)} architectural tiers"],
            fallback=True,
        )

    @staticmethod
    def _fallback_documentation(assessment: MigrationAssessment, translation: TranslationReport) -> AIAnalysisResult:
        doc_parts = [
            f"# Migration Runbook: {translation.source_provider.value} → {translation.target_provider.value}",
            "",
            "## Pre-migration checklist",
            "- [ ] Review all blockers and manual actions",
            "- [ ] Validate network connectivity to target cloud",
            "- [ ] Ensure IAM permissions are configured",
            "- [ ] Back up source infrastructure state",
            "",
            "## Migration phases",
        ]
        for phase in assessment.phases:
            doc_parts.append(f"\n### Phase {phase.phase_number}: {phase.name}")
            doc_parts.append(f"Resources: {len(phase.resource_ids)}")
            for rid in phase.resource_ids[:10]:
                doc_parts.append(f"- [ ] Migrate {rid}")

        doc_parts.extend([
            "",
            "## Rollback procedure",
            "- [ ] Revert DNS/traffic to source",
            "- [ ] Verify source infrastructure is still operational",
            "- [ ] Document rollback reason and lessons learned",
        ])

        return AIAnalysisResult(
            analysis_type=AIAnalysisType.DOCUMENTATION,
            content="\n".join(doc_parts),
            confidence="medium",
            fallback=True,
        )
