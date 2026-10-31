"""Unit tests for the FastF1 credential wiring in the ingest task.

FastF1 refuses anonymous session loads for the current season: the round still
resolves from the public schedule, but the timing data stays empty and the
Bronze build fails with ``DataNotLoadedError``. The job runs with no ambient
environment, so the ingest task has to resolve ``F1_USERNAME``/``F1_PASSWORD``
from the ``f1_secrets`` scope before it loads a session. These tests pin that
contract.
"""

from __future__ import annotations

import pytest

import databricks_entrypoint as entry


def test_credential_env_var_names_match_the_fastf1_contract() -> None:
    """FastF1 reads exactly these two environment variables."""
    assert entry._FASTF1_CREDENTIAL_ENV_VARS == ("F1_USERNAME", "F1_PASSWORD")


def test_run_ingest_loads_fastf1_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ingest task resolves the F1 account pair before touching a session."""
    calls: list[tuple[tuple[str, ...], str]] = []

    def fake_loader(env_vars: tuple[str, ...], label: str) -> None:
        calls.append((env_vars, label))

    monkeypatch.setattr(entry, "_load_secrets_from_databricks", fake_loader)
    monkeypatch.setattr(entry, "_resolve_ingest_rounds", lambda *args, **kwargs: [])

    entry.run_ingest(2026)

    assert calls == [(entry._FASTF1_CREDENTIAL_ENV_VARS, "FastF1 credentials")]
