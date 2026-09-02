"""Root fixtures and collection-time marker assignment.

Every test under `tests/unit/` is auto-marked `unit`, every test under `tests/pg/` is
auto-marked `pg` -- so `pytest -m unit` and `pytest -m pg` select by directory without every
test file repeating `pytestmark`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"
os.environ.setdefault("LIOS_CONFIG_PATH", str(_CONFIG_PATH))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Tag each collected test with `unit` or `pg` based on which directory it lives in."""
    for item in items:
        path = str(item.fspath)
        if f"{os.sep}tests{os.sep}unit{os.sep}" in path:
            item.add_marker(pytest.mark.unit)
        elif f"{os.sep}tests{os.sep}pg{os.sep}" in path:
            item.add_marker(pytest.mark.pg)
