"""Pytest configuration for the test suite."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

_TEMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp_tests"
_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


@pytest.fixture()
def tmp_path() -> Path:
    """Return an isolated writable temporary directory for tests.

    This shadows pytest's built-in ``tmp_path`` fixture to avoid the Windows
    sandbox path/ACL issues observed with ``pytest-of-restr`` in this runtime.
    """

    path = _TEMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
