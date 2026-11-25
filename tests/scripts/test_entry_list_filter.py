"""Tests for the entry-list filter used by the race simulation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.simulate_race import _restrict_to_latest_entry_list


def _stats(drivers: list[str]) -> pd.DataFrame:
    """Build a season-to-date form frame, one row per driver."""
    return pd.DataFrame(
        {
            "Driver": drivers,
            "Team": ["Haas"] * len(drivers),
            "LapTime_s": [95.0] * len(drivers),
        }
    )


def test_drops_drivers_absent_from_the_latest_round(tmp_path: Path) -> None:
    """A driver who stopped racing is not predicted for the next event."""
    stats = _stats(["VER", "OCO", "TSU", "CAM"])
    latest = tmp_path / "race_laps.parquet"
    pd.DataFrame({"Driver": ["VER", "CAM", "VER", "CAM"]}).to_parquet(latest)

    filtered = _restrict_to_latest_entry_list(stats, latest)

    assert filtered["Driver"].tolist() == ["VER", "CAM"]
    assert filtered.index.tolist() == [0, 1]


def test_keeps_everyone_without_a_reference_round() -> None:
    """The first race of a season has no previous entry list to filter on."""
    stats = _stats(["VER", "OCO"])

    filtered = _restrict_to_latest_entry_list(stats, None)

    assert filtered["Driver"].tolist() == ["VER", "OCO"]


def test_ignores_a_reference_without_drivers(tmp_path: Path) -> None:
    """A malformed reference file must not wipe the scenario."""
    stats = _stats(["VER"])
    latest = tmp_path / "race_laps.parquet"
    pd.DataFrame({"Foo": [1]}).to_parquet(latest)

    filtered = _restrict_to_latest_entry_list(stats, latest)

    assert filtered["Driver"].tolist() == ["VER"]
