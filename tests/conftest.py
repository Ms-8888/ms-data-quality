import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def sample_path() -> Path:
    return DATA / "sample_customers.csv"


@pytest.fixture
def truth() -> dict:
    return json.loads((DATA / "sample_customers.truth.json").read_text(encoding="utf-8"))
