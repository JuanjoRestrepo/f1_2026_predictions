"""Tests for the entry-list filter used by the race simulation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.simulate_race import _restrict_to_latest_entry_list, select_scenario_roster


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


def test_restores_a_driver_classified_without_a_timed_lap(tmp_path: Path) -> None:
    """An entered driver who retired before setting a lap is still predicted.

    São Paulo 2026: Bottas was classified but has no lap rows in Gold, so the
    parquet alone would drop him from the next round's roster.
    """
    stats = _stats(["VER", "BOT", "OCO"])
    latest = tmp_path / "race_laps.parquet"
    pd.DataFrame({"Driver": ["VER"]}).to_parquet(latest)
    results = tmp_path / "actual_results_round_20.json"
    results.write_text(
        json.dumps({"results": [{"driver": "VER"}, {"driver": "BOT"}]}),
        encoding="utf-8",
    )

    filtered = _restrict_to_latest_entry_list(stats, latest, results)

    assert filtered["Driver"].tolist() == ["VER", "BOT"]


def test_missing_classification_falls_back_to_the_lap_roster(tmp_path: Path) -> None:
    """No previous report yet: the parquet roster is all that is available."""
    stats = _stats(["VER", "BOT"])
    latest = tmp_path / "race_laps.parquet"
    pd.DataFrame({"Driver": ["VER"]}).to_parquet(latest)

    filtered = _restrict_to_latest_entry_list(
        stats, latest, tmp_path / "does_not_exist.json"
    )

    assert filtered["Driver"].tolist() == ["VER"]


def _classification(path: Path, rows: list[dict[str, str]]) -> Path:
    """Write an official classification fixture."""
    path.write_text(json.dumps({"results": rows}), encoding="utf-8")
    return path


def test_target_classification_drops_phantoms_and_adds_a_debutant(
    tmp_path: Path,
) -> None:
    """A completed round is rostered from its own classification.

    Mexico 2026: Ocon and Tsunoda had already left, and Hadjar debuted with no
    laps of his own. His form is the median of the Haas teammate already in
    the season, under the team name Gold uses.
    """
    stats = _stats(["VER", "BEA", "OCO", "TSU"])
    stats.loc[stats["Driver"] == "VER", "Team"] = "Red Bull"
    stats.loc[stats["Driver"] == "BEA", "Team"] = "Haas"
    stats.loc[stats["Driver"] == "OCO", "Team"] = "Alpine"
    stats.loc[stats["Driver"] == "TSU", "Team"] = "Racing Bulls"
    stats.loc[stats["Driver"] == "BEA", "LapTime_s"] = 96.5
    stats.loc[stats["Driver"] == "VER", "LapTime_s"] = 90.0
    classification = _classification(
        tmp_path / "actual_results_round_19.json",
        [
            {"driver": "VER", "team": "Red Bull Racing"},
            {"driver": "BEA", "team": "Haas F1 Team"},
            {"driver": "HIR", "team": "Haas F1 Team", "status": "Finished"},
        ],
    )
    # The previous round still contains the drivers who had left. It must not
    # decide the roster once this round's classification exists.
    previous_laps = tmp_path / "race_laps.parquet"
    pd.DataFrame({"Driver": ["VER", "OCO", "TSU"]}).to_parquet(previous_laps)

    roster = select_scenario_roster(
        stats,
        target_results_file=classification,
        latest_round_file=previous_laps,
        previous_results_file=None,
    )

    assert roster["Driver"].tolist() == ["VER", "BEA", "HIR"]
    debutant = roster.loc[roster["Driver"] == "HIR"].iloc[0]
    assert debutant["Team"] == "Haas"
    assert debutant["LapTime_s"] == 96.5


def test_target_classification_keeps_a_driver_who_did_not_start(
    tmp_path: Path,
) -> None:
    """A DNS is in the classification, so the pre-race roster still includes them."""
    stats = _stats(["VER", "BOT"])
    classification = _classification(
        tmp_path / "actual_results_round_20.json",
        [
            {"driver": "VER", "team": "Red Bull Racing", "status": "Finished"},
            {"driver": "BOT", "team": "Cadillac", "status": "Did not start"},
        ],
    )

    roster = select_scenario_roster(
        stats,
        target_results_file=classification,
        latest_round_file=None,
    )

    assert roster["Driver"].tolist() == ["VER", "BOT"]


def test_missing_target_classification_uses_the_previous_round(
    tmp_path: Path,
) -> None:
    """A race that has not been run yet keeps the previous-round entry proxy."""
    stats = _stats(["VER", "OCO"])
    latest = tmp_path / "race_laps.parquet"
    pd.DataFrame({"Driver": ["VER"]}).to_parquet(latest)

    roster = select_scenario_roster(
        stats,
        target_results_file=tmp_path / "actual_results_round_22.json",
        latest_round_file=latest,
    )

    assert roster["Driver"].tolist() == ["VER"]
