"""Tests for the lap-position artifact built from a race session."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.master_pipeline import generate_lap_data, generate_predicted_lap_data


class _FakeLaps:
    """Subset of FastF1's ``Laps`` that supports ``pick_drivers``."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def pick_drivers(self, driver: str) -> pd.DataFrame:
        return self._frame[self._frame["Driver"] == driver]


class _FakeSession:
    """Only the attributes ``generate_lap_data`` reads."""

    def __init__(self, laps: pd.DataFrame, results: pd.DataFrame) -> None:
        self.laps = _FakeLaps(laps)
        self.results = results
        self.event = {
            "EventName": "Test Grand Prix",
            "EventDate": pd.Timestamp("2026-11-21"),
        }


def _laps(driver: str, last_lap: int) -> list[dict[str, object]]:
    """One row per completed lap, finishing position equal to the lap number."""
    return [
        {
            "Driver": driver,
            "Team": "Test Team",
            "LapNumber": lap,
            "Position": float(lap),
        }
        for lap in range(1, last_lap + 1)
    ]


def test_retired_driver_series_stops_at_the_last_completed_lap() -> None:
    """A retirement must not be drawn across the remaining race distance."""
    laps = pd.DataFrame(_laps("VER", 50) + _laps("PER", 18))
    results = pd.DataFrame(
        [
            {"Abbreviation": "VER", "Position": 1.0},
            {"Abbreviation": "PER", "Position": 21.0},
            {"Abbreviation": "ALB", "Position": np.nan},
        ]
    )
    session = _FakeSession(laps, results)

    data = generate_lap_data(session, ["VER", "PER", "ALB"], total_laps=50)

    by_driver = {entry["driver"]: entry for entry in data["drivers"]}
    assert "ALB" not in by_driver  # did not start: no lap chart entry
    assert len(by_driver["PER"]["positions"]) == 18
    assert by_driver["PER"]["positions"]["18"] == 18
    assert "19" not in by_driver["PER"]["positions"]
    assert "50" not in by_driver["PER"]["positions"]


def test_classified_finisher_keeps_the_official_final_position() -> None:
    """The final lap is synced to the classification for a finisher."""
    laps = pd.DataFrame(_laps("VER", 50))
    results = pd.DataFrame([{"Abbreviation": "VER", "Position": 3.0}])
    session = _FakeSession(laps, results)

    data = generate_lap_data(session, ["VER"], total_laps=50)

    positions = data["drivers"][0]["positions"]
    assert positions["49"] == 49
    assert positions["50"] == 3


def test_predicted_lap_data_excludes_drivers_outside_predicted_order() -> None:
    """DNS drivers absent from predicted_order must not appear in the chart.

    Regression guard for R01/R02 where phantom entries (HUL, PIA, ALB, BOR)
    appeared in the Predicted tab because the loop iterated ``all_drivers``
    instead of ``predicted_order``.
    """
    # ALB is in all_drivers (he was listed in the entry list) but NOT in
    # predicted_order because the model never scored him (DNS).
    laps = pd.DataFrame(
        _laps("VER", 10) + _laps("LEC", 10)
        # ALB did not start, so he has zero laps in the session
    )
    results = pd.DataFrame(
        [
            {"Abbreviation": "VER", "Position": 1.0},
            {"Abbreviation": "LEC", "Position": 2.0},
            {"Abbreviation": "ALB", "Position": np.nan},
        ]
    )
    session = _FakeSession(laps, results)

    all_drivers = ["VER", "LEC", "ALB"]
    predicted_order = ["VER", "LEC"]  # ALB deliberately excluded

    data = generate_predicted_lap_data(
        session,
        all_drivers=all_drivers,
        total_laps=10,
        predicted_order=predicted_order,
    )

    returned_drivers = {entry["driver"] for entry in data["drivers"]}
    assert returned_drivers == {"VER", "LEC"}, (
        f"Expected only predicted drivers {{VER, LEC}}, got {returned_drivers}"
    )
    # DNS driver must be excluded from predicted chart
    assert "ALB" not in returned_drivers
