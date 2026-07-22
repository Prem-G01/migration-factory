from __future__ import annotations

import json
from pathlib import Path

import pytest

from migration_factory.core.exceptions import TranslationError
from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
    SourceLocation,
)
from migration_factory.domain.enums import CanonicalResourceType, CloudProvider
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import (
    CapabilityMatrix,
    load_builtin_matrix,
    load_matrix,
)
from migration_factory.translation.models import SupportStatus

# --- helpers ---

def _loc() -> SourceLocation:
    return SourceLocation(source_system="test", source_path="test")


def _resource(
    rid: str,
    ctype: CanonicalResourceType,
    depends_on: frozenset[str] = frozenset(),
) -> CanonicalResource:
    return CanonicalResource(
        id=rid,
        canonical_type=ctype,
        source_provider=CloudProvider.AWS,
        source_type=f"aws_{ctype.value.replace('.', '_')}",
        name=rid,
        depends_on=depends_on,
        source_location=_loc(),
    )


# --- Matrix loading ---

class TestCapabilityMatrixLoading:
    def test_load_builtin_aws_to_gcp(self) -> None:
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)

        assert matrix.source_provider is CloudProvider.AWS
        assert matrix.target_provider is CloudProvider.GCP
        assert len(matrix.rules) >= 8

    def test_load_nonexistent_provider_pair_raises(self) -> None:
        with pytest.raises(TranslationError, match="No built-in capability matrix"):
            load_builtin_matrix(CloudProvider.AWS, CloudProvider.AZURE)

    def test_load_external_matrix(self, tmp_path: Path) -> None:
        raw = {
            "matrix_version": "0.1.0",
            "source_provider": "aws",
            "target_provider": "gcp",
            "rules": [
                {
                    "canonical_type": "compute.instance",
                    "target_service": "Compute Engine",
                    "target_terraform_types": ["google_compute_instance"],
                    "status": "supported",
                    "rationale": "Direct VM-to-VM mapping via machine-type lookup table.",
                    "complexity_weight": 5,
                }
            ],
        }
        path = tmp_path / "custom.json"
        path.write_text(json.dumps(raw))

        matrix = load_matrix(path)
        assert len(matrix.rules) == 1
        assert matrix.rules[0].canonical_type is CanonicalResourceType.COMPUTE_INSTANCE

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{ not json")
        with pytest.raises(TranslationError, match="not valid JSON"):
            load_matrix(bad)

    def test_placeholder_rationale_rejected(self, tmp_path: Path) -> None:
        raw = {
            "matrix_version": "0.1.0",
            "source_provider": "aws",
            "target_provider": "gcp",
            "rules": [
                {
                    "canonical_type": "compute.instance",
                    "target_service": "Compute Engine",
                    "status": "supported",
                    "rationale": "TBD",
                    "complexity_weight": 5,
                }
            ],
        }
        path = tmp_path / "placeholder.json"
        path.write_text(json.dumps(raw))
        with pytest.raises(TranslationError, match="failed schema validation"):
            load_matrix(path)

    def test_duplicate_canonical_type_rejected(self, tmp_path: Path) -> None:
        rule = {
            "canonical_type": "compute.instance",
            "target_service": "Compute Engine",
            "status": "supported",
            "rationale": "This is a valid rationale for the mapping.",
            "complexity_weight": 5,
        }
        raw = {
            "matrix_version": "0.1.0",
            "source_provider": "aws",
            "target_provider": "gcp",
            "rules": [rule, rule],
        }
        path = tmp_path / "dup.json"
        path.write_text(json.dumps(raw))
        with pytest.raises(TranslationError, match="duplicate"):
            load_matrix(path)

    def test_every_builtin_rule_has_non_placeholder_rationale(self) -> None:
        matrix = load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)
        for rule in matrix.rules:
            assert len(rule.rationale) >= 10, f"{rule.canonical_type}: rationale too short"


# --- Translation Engine ---

class TestTranslationEngine:
    @pytest.fixture()
    def matrix(self) -> CapabilityMatrix:
        return load_builtin_matrix(CloudProvider.AWS, CloudProvider.GCP)

    def test_supported_resource_gets_target_service(
        self, matrix: CapabilityMatrix
    ) -> None:
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))

        engine = TranslationEngine(matrix=matrix)
        report = engine.translate(graph)

        assert len(report.results) == 1
        r = report.results[0]
        assert r.status is SupportStatus.SUPPORTED
        assert r.target_service == "VPC Network"
        assert "google_compute_network" in r.target_terraform_types
        assert len(r.rationale) > 10

    def test_partial_resource_carries_required_changes(
        self, matrix: CapabilityMatrix
    ) -> None:
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(
            _resource("sg", CanonicalResourceType.NETWORK_FIREWALL_RULE)
        )

        report = TranslationEngine(matrix=matrix).translate(graph)

        r = report.results[0]
        assert r.status is SupportStatus.PARTIAL
        assert len(r.required_changes) > 0

    def test_manual_resource_carries_manual_actions(
        self, matrix: CapabilityMatrix
    ) -> None:
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE))

        report = TranslationEngine(matrix=matrix).translate(graph)

        r = report.results[0]
        assert r.status is SupportStatus.MANUAL
        assert len(r.manual_actions) > 0

    def test_unmapped_canonical_type_gets_unsupported_with_rationale(
        self, matrix: CapabilityMatrix
    ) -> None:
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("x", CanonicalResourceType.UNSUPPORTED))

        report = TranslationEngine(matrix=matrix).translate(graph)

        r = report.results[0]
        assert r.status is SupportStatus.UNSUPPORTED
        assert "No translation rule" in r.rationale

    def test_mixed_provider_graph_raises(self, matrix: CapabilityMatrix) -> None:
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        gcp_resource = CanonicalResource(
            id="gcp:x",
            canonical_type=CanonicalResourceType.COMPUTE_INSTANCE,
            source_provider=CloudProvider.GCP,
            source_type="google_compute_instance",
            name="x",
            source_location=_loc(),
        )
        graph.add_resource(gcp_resource)

        with pytest.raises(TranslationError, match="do not match"):
            TranslationEngine(matrix=matrix).translate(graph)

    def test_summary_counts_all_statuses(
        self, matrix: CapabilityMatrix
    ) -> None:
        graph = CanonicalInfrastructureGraph()
        graph.add_resource(_resource("vpc", CanonicalResourceType.NETWORK_VPC))
        graph.add_resource(_resource("sg", CanonicalResourceType.NETWORK_FIREWALL_RULE))
        graph.add_resource(_resource("role", CanonicalResourceType.IAM_ROLE))

        report = TranslationEngine(matrix=matrix).translate(graph)

        s = report.summary
        assert s["supported"] == 1
        assert s["partial"] == 1
        assert s["manual"] == 1

    def test_empty_graph_produces_empty_report(
        self, matrix: CapabilityMatrix
    ) -> None:
        graph = CanonicalInfrastructureGraph()
        report = TranslationEngine(matrix=matrix).translate(graph)
        assert report.results == []
