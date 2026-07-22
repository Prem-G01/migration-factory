"""FastAPI REST layer tests — exercised in-process via TestClient, no server
needed. Covers all 7 endpoints across the AWS->GCP, GCP->AWS, and
analyze-only cases.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from migration_factory.api.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_analyze_aws_to_gcp(sample_tfstate_path: Path) -> None:
    with sample_tfstate_path.open("rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("sample_terraform.tfstate", f, "application/json")},
            data={"target": "gcp"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["direction"] == "AWS → GCP"
    assert data["summary"]["resources"] == 6


def test_analyze_gcp_to_aws(sample_gcp_tfstate_path: Path) -> None:
    with sample_gcp_tfstate_path.open("rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("sample_gcp.tfstate", f, "application/json")},
            data={"target": "aws"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["direction"] == "GCP → AWS"


def test_analyze_only_mode(sample_tfstate_path: Path) -> None:
    with sample_tfstate_path.open("rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("sample_terraform.tfstate", f, "application/json")},
        )
    assert response.status_code == 200
    data = response.json()
    assert "terraform" not in data

    # No Terraform should exist for this run
    tf_response = client.get(f"/api/v1/terraform/{data['run_id']}")
    assert tf_response.status_code == 404


def test_get_report(sample_tfstate_path: Path) -> None:
    with sample_tfstate_path.open("rb") as f:
        analyze_response = client.post(
            "/api/v1/analyze",
            files={"file": ("sample_terraform.tfstate", f, "application/json")},
            data={"target": "gcp"},
        )
    run_id = analyze_response.json()["run_id"]

    report_response = client.get(f"/api/v1/report/{run_id}")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["run_id"] == run_id
    assert "assessment" in report
    assert "security" in report
    assert "compliance" in report
    assert "finops" in report


def test_get_html_report(sample_tfstate_path: Path) -> None:
    with sample_tfstate_path.open("rb") as f:
        analyze_response = client.post(
            "/api/v1/analyze",
            files={"file": ("sample_terraform.tfstate", f, "application/json")},
            data={"target": "gcp"},
        )
    run_id = analyze_response.json()["run_id"]

    html_response = client.get(f"/api/v1/report/{run_id}/html")
    assert html_response.status_code == 200
    assert html_response.headers["content-type"].startswith("text/html")
    assert "<html" in html_response.text.lower()


def test_get_terraform_zip(sample_tfstate_path: Path) -> None:
    with sample_tfstate_path.open("rb") as f:
        analyze_response = client.post(
            "/api/v1/analyze",
            files={"file": ("sample_terraform.tfstate", f, "application/json")},
            data={"target": "gcp"},
        )
    run_id = analyze_response.json()["run_id"]

    tf_response = client.get(f"/api/v1/terraform/{run_id}")
    assert tf_response.status_code == 200
    assert tf_response.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(BytesIO(tf_response.content))
    assert "main.tf" in zf.namelist()


def test_terraform_not_available_for_analyze_only(sample_gcp_tfstate_path: Path) -> None:
    with sample_gcp_tfstate_path.open("rb") as f:
        analyze_response = client.post(
            "/api/v1/analyze",
            files={"file": ("sample_gcp.tfstate", f, "application/json")},
            data={"target": "analyze_only"},
        )
    run_id = analyze_response.json()["run_id"]

    tf_response = client.get(f"/api/v1/terraform/{run_id}")
    assert tf_response.status_code == 404


def test_list_runs(sample_tfstate_path: Path) -> None:
    with sample_tfstate_path.open("rb") as f:
        client.post(
            "/api/v1/analyze",
            files={"file": ("sample_terraform.tfstate", f, "application/json")},
            data={"target": "gcp"},
        )

    runs_response = client.get("/api/v1/runs")
    assert runs_response.status_code == 200
    runs = runs_response.json()["runs"]
    assert len(runs) >= 1
    assert "run_id" in runs[0]
    assert "direction" in runs[0]


def test_invalid_run_id() -> None:
    response = client.get("/api/v1/report/nonexistent")
    assert response.status_code == 404


def test_unsupported_file_format() -> None:
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("malware.exe", b"\x4d\x5a\x90\x00not-a-real-exe", "application/octet-stream")},
        data={"target": "gcp"},
    )
    assert response.status_code == 400


def test_delete_run(sample_tfstate_path: Path) -> None:
    with sample_tfstate_path.open("rb") as f:
        analyze_response = client.post(
            "/api/v1/analyze",
            files={"file": ("sample_terraform.tfstate", f, "application/json")},
            data={"target": "gcp"},
        )
    run_id = analyze_response.json()["run_id"]

    delete_response = client.delete(f"/api/v1/runs/{run_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    assert client.get(f"/api/v1/report/{run_id}").status_code == 404
