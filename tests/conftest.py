from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_tfstate_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_terraform.tfstate"
