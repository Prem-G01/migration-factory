"""AI Chat Interface (CLI) and Smoke Test Framework.

The chat interface is a CLI REPL that wraps the AIEngine for interactive
infrastructure Q&A. The smoke test framework runs automated checks
against deployed (or simulated) infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.ai.engine import AIEngine
from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.assessment.models import MigrationAssessment
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.domain.enums import CloudProvider
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
from migration_factory.translation.models import TranslationReport

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# AI Chat Interface
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str  # "user" or "assistant"
    content: str


class ChatSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(default_factory=list)
    graph: CanonicalInfrastructureGraph | None = None
    translation: TranslationReport | None = None
    assessment: MigrationAssessment | None = None


@dataclass(slots=True)
class AIChatInterface:
    """Interactive CLI chat for infrastructure Q&A powered by AIEngine."""

    ai_engine: AIEngine = field(default_factory=AIEngine)
    session: ChatSession = field(default_factory=ChatSession)

    def load_context(
        self,
        graph: CanonicalInfrastructureGraph,
        translation: TranslationReport | None = None,
        assessment: MigrationAssessment | None = None,
    ) -> None:
        """Load infrastructure context for the chat session."""
        self.session.graph = graph
        self.session.translation = translation
        self.session.assessment = assessment

    def ask(self, question: str) -> str:
        """Process a user question and return AI response."""
        self.session.messages.append(ChatMessage(role="user", content=question))

        if self.session.graph is None:
            response = "No infrastructure loaded. Use load_context() first."
        elif "explain" in question.lower() or "what" in question.lower():
            result = self.ai_engine.explain_infrastructure(self.session.graph)
            response = result.content
        elif "risk" in question.lower() or "danger" in question.lower():
            if self.session.translation and self.session.assessment:
                result = self.ai_engine.analyze_migration_risks(
                    self.session.graph, self.session.translation, self.session.assessment
                )
                response = result.content
            else:
                response = "Translation and assessment needed for risk analysis. Run the full pipeline first."
        elif "optim" in question.lower() or "cost" in question.lower() or "save" in question.lower():
            if self.session.translation:
                result = self.ai_engine.suggest_optimizations(
                    self.session.graph, self.session.translation, 500.0, 420.0
                )
                response = result.content
            else:
                response = "Translation needed for optimization analysis."
        elif "architect" in question.lower() or "summary" in question.lower():
            result = self.ai_engine.generate_architecture_summary(self.session.graph)
            response = result.content
        elif "doc" in question.lower() or "runbook" in question.lower():
            if self.session.translation and self.session.assessment:
                result = self.ai_engine.generate_documentation(
                    self.session.graph, self.session.translation, self.session.assessment
                )
                response = result.content
            else:
                response = "Full pipeline needed for documentation generation."
        else:
            result = self.ai_engine.explain_infrastructure(self.session.graph)
            response = f"Here's what I know about your infrastructure:\n\n{result.content}"

        self.session.messages.append(ChatMessage(role="assistant", content=response))
        return response

    def run_repl(self) -> None:
        """Run an interactive REPL. Blocking — for CLI use."""
        print("Migration Factory AI Chat")
        print("Type 'quit' to exit, 'help' for available commands.\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in {"quit", "exit", "q"}:
                print("Goodbye!")
                break
            if user_input.lower() == "help":
                print("Commands: explain, risks, optimize, architecture, documentation, quit")
                continue
            if user_input.lower() == "history":
                for msg in self.session.messages:
                    print(f"[{msg.role}] {msg.content[:100]}...")
                continue

            response = self.ask(user_input)
            print(f"\nAssistant: {response}\n")


# ---------------------------------------------------------------------------
# Smoke Test Framework
# ---------------------------------------------------------------------------


class SmokeTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_name: str
    passed: bool
    message: str
    duration_ms: float = 0


class SmokeTestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all_passed: bool = True
    tests: list[SmokeTestResult] = Field(default_factory=list)
    total_tests: int = 0
    passed_count: int = 0
    failed_count: int = 0


@dataclass(slots=True)
class SmokeTestRunner:
    """Runs smoke tests against deployed or simulated infrastructure."""

    simulation: bool = True

    def run(self, graph: CanonicalInfrastructureGraph) -> SmokeTestReport:
        """Run all smoke tests."""
        import time
        tests: list[SmokeTestResult] = []

        # Test 1: Graph is non-empty
        start = time.monotonic()
        tests.append(SmokeTestResult(
            test_name="graph_not_empty",
            passed=len(graph.resources) > 0,
            message=f"{len(graph.resources)} resources in graph",
            duration_ms=round((time.monotonic() - start) * 1000, 2),
        ))

        # Test 2: No circular dependencies
        start = time.monotonic()
        try:
            graph.topological_order()
            tests.append(SmokeTestResult(
                test_name="no_circular_dependencies",
                passed=True, message="Topological order computed successfully",
                duration_ms=round((time.monotonic() - start) * 1000, 2),
            ))
        except Exception as exc:
            tests.append(SmokeTestResult(
                test_name="no_circular_dependencies",
                passed=False, message=str(exc),
                duration_ms=round((time.monotonic() - start) * 1000, 2),
            ))

        # Test 3: All resources have valid canonical types
        start = time.monotonic()
        from migration_factory.domain.enums import CanonicalResourceType
        invalid = [r.id for r in graph.resources.values() if r.canonical_type is CanonicalResourceType.UNSUPPORTED]
        tests.append(SmokeTestResult(
            test_name="all_types_valid",
            passed=len(invalid) == 0,
            message=f"{len(invalid)} unsupported types" if invalid else "All types valid",
            duration_ms=round((time.monotonic() - start) * 1000, 2),
        ))

        # Test 4: Translation works
        start = time.monotonic()
        try:
            providers = {r.source_provider for r in graph.resources.values()}
            if CloudProvider.AWS in providers:
                matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
                translation = TranslationEngine(matrix=matrix).translate(graph)
                tests.append(SmokeTestResult(
                    test_name="translation_succeeds",
                    passed=True, message=f"{len(translation.results)} resources translated",
                    duration_ms=round((time.monotonic() - start) * 1000, 2),
                ))
            else:
                tests.append(SmokeTestResult(
                    test_name="translation_succeeds",
                    passed=True, message="No AWS resources to translate",
                    duration_ms=round((time.monotonic() - start) * 1000, 2),
                ))
        except Exception as exc:
            tests.append(SmokeTestResult(
                test_name="translation_succeeds",
                passed=False, message=str(exc),
                duration_ms=round((time.monotonic() - start) * 1000, 2),
            ))

        # Test 5: Assessment works
        start = time.monotonic()
        try:
            providers = {r.source_provider for r in graph.resources.values()}
            if CloudProvider.AWS in providers:
                matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
                translation = TranslationEngine(matrix=matrix).translate(graph)
                assessment = AssessmentEngine().assess(graph, translation)
                tests.append(SmokeTestResult(
                    test_name="assessment_succeeds",
                    passed=assessment.overall_complexity_score > 0,
                    message=f"Score: {assessment.overall_complexity_score}/100",
                    duration_ms=round((time.monotonic() - start) * 1000, 2),
                ))
            else:
                tests.append(SmokeTestResult(
                    test_name="assessment_succeeds",
                    passed=True, message="Skipped (no AWS resources)",
                    duration_ms=round((time.monotonic() - start) * 1000, 2),
                ))
        except Exception as exc:
            tests.append(SmokeTestResult(
                test_name="assessment_succeeds",
                passed=False, message=str(exc),
                duration_ms=round((time.monotonic() - start) * 1000, 2),
            ))

        passed = sum(1 for t in tests if t.passed)
        failed = sum(1 for t in tests if not t.passed)

        return SmokeTestReport(
            all_passed=failed == 0, tests=tests,
            total_tests=len(tests), passed_count=passed, failed_count=failed,
        )
