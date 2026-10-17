"""Unit tests for the pace normalisation in scripts/simulate_race.py.

The simulator translates a driver's season median onto the target circuit's
lap-time scale. That translation used to subtract a *pooled* season median,
which mostly measures which circuits a driver happened to have laps at: the
current-season window mixes circuits whose lap times differ by more than ten
seconds, so a driver with no laps at a short track read as seconds per lap
slower than a team-mate with no laps at a long one.

These tests pin the corrected behaviour: pace is measured against each round's
own baseline, one observation per round, so track mix cannot masquerade as pace.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.simulate_race import (
    _apply_track_pace_normalization,
    _driver_track_normalized_deltas,
)

_FAST_DRIVER = "FAST"
_SLOW_DRIVER = "SLOW"


def _laps(rows: list[tuple[str, int, float, bool]]) -> pd.DataFrame:
    """Build a lap frame from ``(driver, round, lap_time, rainy)`` tuples."""
    return pd.DataFrame(
        [
            {"Driver": driver, "RoundNumber": rnd, "LapTime_s": time, "Rainfall": wet}
            for driver, rnd, time, wet in rows
        ]
    )


def _current_laps() -> pd.DataFrame:
    """A two-circuit window with deliberately unbalanced lap counts.

    Round 1 is a short circuit (~80s), round 2 a long one (~100s). The fast
    driver has eight laps at the short circuit and only two at the long one; the
    slow driver is the other way round.
    """
    return _laps(
        [(_FAST_DRIVER, 1, 80.0, False)] * 8
        + [(_SLOW_DRIVER, 1, 81.0, False)] * 8
        + [(_FAST_DRIVER, 2, 100.5, False)] * 2
        + [(_SLOW_DRIVER, 2, 100.0, False)] * 8
    )


def _sim(drivers: list[str]) -> pd.DataFrame:
    """A simulation scenario with the pace columns the normaliser writes to."""
    return pd.DataFrame(
        [
            {
                "Driver": driver,
                "roll_laptime_3": 90.0,
                "roll_laptime_5": 90.0,
                "Sector1Time_s": 30.0,
                "Sector2Time_s": 31.0,
                "Sector3Time_s": 29.0,
            }
            for driver in drivers
        ]
    )


def _gold(event: str, lap_time: float) -> pd.DataFrame:
    """Historical laps for a target circuit, at a known baseline."""
    return pd.DataFrame(
        [{"EventName": event, "LapTime_s": lap_time, "Rainfall": False}] * 20
    )


def test_pooled_median_is_confounded_but_per_track_delta_is_not() -> None:
    """The whole point of the fix, in one assertion pair."""
    current = _current_laps()

    deltas = _driver_track_normalized_deltas(current, is_wet_race=False)
    assert deltas[_FAST_DRIVER] == pytest.approx(0.0)
    assert deltas[_SLOW_DRIVER] == pytest.approx(0.25)
    assert deltas.max() - deltas.min() == pytest.approx(0.25)

    # What the old code used: a median pooled across both circuits, which puts
    # these two drivers 10.5s apart purely because of lap-count mix.
    pooled = current.groupby("Driver")["LapTime_s"].median()
    assert pooled[_SLOW_DRIVER] - pooled[_FAST_DRIVER] == pytest.approx(10.5)


def test_target_pace_is_the_track_baseline_plus_the_driver_delta() -> None:
    """The delta lands on the target circuit's level, not the window's."""
    out = _apply_track_pace_normalization(
        _sim([_FAST_DRIVER, _SLOW_DRIVER]),
        "Canada Grand Prix",
        _gold("Canada Grand Prix", 78.0),
        _current_laps(),
        is_wet_race=False,
    ).set_index("Driver")

    assert out.loc[_FAST_DRIVER, "roll_laptime_3"] == pytest.approx(78.0)
    assert out.loc[_SLOW_DRIVER, "roll_laptime_3"] == pytest.approx(78.25)
    # roll_laptime_5 mirrors roll_laptime_3, as before.
    assert out.loc[_FAST_DRIVER, "roll_laptime_5"] == pytest.approx(78.0)


def test_sectors_are_scaled_once_for_the_whole_field() -> None:
    """Sector scale is a circuit-to-circuit ratio, not a per-driver fudge."""
    current = _current_laps()
    out = _apply_track_pace_normalization(
        _sim([_FAST_DRIVER, _SLOW_DRIVER]),
        "Canada Grand Prix",
        _gold("Canada Grand Prix", 78.0),
        current,
        is_wet_race=False,
    )

    window_median = current["LapTime_s"].median()
    expected_scale = 78.0 / window_median

    scales = (out["Sector1Time_s"] / 30.0).tolist()
    assert scales[0] == pytest.approx(expected_scale)
    assert scales[1] == pytest.approx(expected_scale)
    assert out["Sector3Time_s"].iloc[0] == pytest.approx(29.0 * expected_scale)


def test_driver_with_no_laps_falls_back_to_the_field_delta() -> None:
    """An unknown driver is neither flattered nor buried."""
    out = _apply_track_pace_normalization(
        _sim([_FAST_DRIVER, _SLOW_DRIVER, "GHOST"]),
        "Canada Grand Prix",
        _gold("Canada Grand Prix", 78.0),
        _current_laps(),
        is_wet_race=False,
    ).set_index("Driver")

    # median of the two known deltas (0.0, 0.25)
    assert out.loc["GHOST", "roll_laptime_3"] == pytest.approx(78.125)


def test_missing_historical_laps_fall_back_to_the_window_median() -> None:
    """An unknown target circuit lands the field on the window's level."""
    out = _apply_track_pace_normalization(
        _sim([_FAST_DRIVER]),
        "Never Raced Grand Prix",
        _gold("Some Other Grand Prix", 78.0),
        _current_laps(),
        is_wet_race=False,
    )

    assert out["roll_laptime_3"].iloc[0] == pytest.approx(81.0)


def test_wet_and_dry_laps_are_measured_separately() -> None:
    """The weather split applies to the driver deltas, not just the baseline."""
    current = _laps(
        [(_FAST_DRIVER, 1, 90.0, True)] * 2
        + [(_SLOW_DRIVER, 1, 91.0, True)] * 2
        + [(_FAST_DRIVER, 2, 100.0, True)] * 2
        + [(_SLOW_DRIVER, 2, 100.0, True)] * 2
        + [(_FAST_DRIVER, 1, 80.0, False)] * 2
        + [(_SLOW_DRIVER, 1, 99.0, False)] * 2
        + [(_FAST_DRIVER, 2, 100.0, False)] * 2
        + [(_SLOW_DRIVER, 2, 100.0, False)] * 2
    )

    wet = _driver_track_normalized_deltas(current, is_wet_race=True)
    dry = _driver_track_normalized_deltas(current, is_wet_race=False)

    assert wet[_FAST_DRIVER] == pytest.approx(-0.25)
    assert wet[_SLOW_DRIVER] == pytest.approx(0.25)
    assert dry[_FAST_DRIVER] == pytest.approx(-4.75)


def test_empty_window_is_a_graceful_no_op() -> None:
    """No usable laps means no delta — not an exception."""
    current = _laps([(_FAST_DRIVER, 1, float("nan"), False)])
    sim = _sim([_FAST_DRIVER, _SLOW_DRIVER])

    deltas = _driver_track_normalized_deltas(current, is_wet_race=False)
    assert deltas.empty

    out = _apply_track_pace_normalization(
        sim, "Canada Grand Prix", _gold("Canada Grand Prix", 78.0), current
    )
    assert out["roll_laptime_3"].tolist() == [78.0, 78.0]
    # season_global_median is NaN here, so the sector scale must be neutral.
    assert out["Sector1Time_s"].tolist() == [30.0, 30.0]


_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "outputs" / "laps"
_lap_files = sorted(_DATA_DIR.glob("season=*/**/*.parquet"))


@pytest.mark.skipif(not _lap_files, reason="local lap data not ingested")
def test_real_window_shows_the_artefact_the_fix_removes() -> None:
    """Guard the fix against the data that produced the 13s spread."""
    current = pd.concat([pd.read_parquet(path) for path in _lap_files])

    pooled = current.groupby("Driver")["LapTime_s"].median()
    deltas = _driver_track_normalized_deltas(current, is_wet_race=False)

    assert pooled.max() - pooled.min() > 10.0
    assert deltas.max() - deltas.min() < (pooled.max() - pooled.min()) / 2
