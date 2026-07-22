from __future__ import annotations

import json
from pathlib import Path

import pytest

from migration_factory.cli import main
from migration_factory.core.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_singleton() -> None:
    """The CLI reads the process-wide settings singleton; force a clean
    rebuild before each test so no prior test's monkeypatched env leaks in.
    """
    get_settings(force_reload=True)


def test_ingest_command_prints_json_report_to_stdout(
    sample_tfstate_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["ingest", str(sample_tfstate_path)])

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 0
    assert report["parser_used"] == "terraform_state"
    assert len(report["graph"]["resources"]) == 6


def test_ingest_command_writes_report_to_output_file(
    sample_tfstate_path: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "report.json"

    exit_code = main(["ingest", str(sample_tfstate_path), "--output", str(output_path)])

    assert exit_code == 0
    assert output_path.exists()
    report = json.loads(output_path.read_text())
    assert report["parser_used"] == "terraform_state"


def test_ingest_command_on_missing_file_returns_error_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_path = tmp_path / "does_not_exist.tfstate"

    exit_code = main(["ingest", str(missing_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ERROR" in captured.err


def test_no_subcommand_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main([])
