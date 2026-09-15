"""Unit tests for f1_predictions.features.clean_air_pace."""

import numpy as np
import pandas as pd

from f1_predictions.features.clean_air_pace import (
    active_intervals,
    candidate_long_run_laps,
    prepare_laps,
    reject_driver_errors,
    robust_spread,
    summarize_clean_air,
    traffic_margins,
)


class MockSession:
    """Mock FastF1 session with laps DataFrame."""

    def __init__(self, laps: pd.DataFrame) -> None:
        self.laps = laps


def test_prepare_laps() -> None:
    """Test prepare_laps converts LapTime, LapStartTime, and Time to seconds."""
    laps_data = pd.DataFrame(
        {
            "LapTime": pd.to_timedelta([90, 91], unit="s"),
            "LapStartTime": pd.to_timedelta([0, 90], unit="s"),
            "Time": pd.to_timedelta([90, 181], unit="s"),
        }
    )
    session = MockSession(laps_data)
    prepared = prepare_laps(session)

    assert "lap_seconds" in prepared.columns
    assert "start_seconds" in prepared.columns
    assert "end_seconds" in prepared.columns
    assert prepared["lap_seconds"].iloc[0] == 90.0
    assert prepared["lap_seconds"].iloc[1] == 91.0


def test_active_intervals() -> None:
    """Test active_intervals filters out in/out laps and retains valid timed laps."""
    laps_df = pd.DataFrame(
        {
            "Driver": ["VER", "VER", "HAM"],
            "LapNumber": [1, 2, 1],
            "start_seconds": [0.0, 100.0, 10.0],
            "end_seconds": [90.0, 190.0, 100.0],
            "PitOutTime": [pd.NaT, pd.NaT, pd.NaT],
            "PitInTime": [pd.NaT, pd.NaT, pd.NaT],
        }
    )
    intervals = active_intervals(laps_df)
    assert "VER" in intervals
    assert "HAM" in intervals
    assert intervals["VER"].shape[0] == 2


def test_traffic_margins() -> None:
    """Test traffic_margins computes distance to car ahead and nearest car."""
    intervals = {
        "VER": np.array([[1.0, 0.0, 90.0]]),
        "HAM": np.array([[1.0, 5.0, 95.0]]),
    }
    ahead, nearest = traffic_margins("VER", 1.0, 0.0, 90.0, intervals)
    assert isinstance(ahead, float)
    assert isinstance(nearest, float)


def test_candidate_long_run_laps() -> None:
    """Test candidate_long_run_laps filters accurate stint laps."""
    laps = pd.DataFrame(
        {
            "Driver": ["VER"] * 5,
            "Stint": [1] * 5,
            "LapNumber": [1, 2, 3, 4, 5],
            "LapTime": [pd.Timedelta(seconds=90)] * 5,
            "IsAccurate": [True] * 5,
            "PitOutTime": [pd.NaT] * 5,
            "PitInTime": [pd.NaT] * 5,
            "TrackStatus": ["1"] * 5,
            "lap_seconds": [90.0, 90.2, 90.1, 90.3, 90.4],
            "start_seconds": [0.0, 90.0, 180.0, 270.0, 360.0],
            "end_seconds": [90.0, 180.0, 270.0, 360.0, 450.0],
            "Compound": ["MEDIUM"] * 5,
            "TyreLife": [1, 2, 3, 4, 5],
        }
    )
    candidates = candidate_long_run_laps(laps)
    assert not candidates.empty
    assert "clean_air" in candidates.columns
    assert len(candidates) == 5


def test_reject_driver_errors() -> None:
    """Test reject_driver_errors removes outlier error laps."""
    clean_laps = pd.DataFrame(
        {
            "driver": ["VER"] * 6,
            "stint": [1] * 6,
            "lap_seconds": [
                90.0,
                90.1,
                90.2,
                90.1,
                90.0,
                105.0,
            ],  # 105s is a lockup error
        }
    )
    filtered = reject_driver_errors(clean_laps)
    assert len(filtered) == 5
    assert 105.0 not in filtered["lap_seconds"].values


def test_robust_spread() -> None:
    """Test robust_spread calculates MAD spread."""
    s = pd.Series([90.0, 90.1, 90.2, 90.1, 90.0])
    spread = robust_spread(s)
    assert spread >= 0.0


def test_summarize_clean_air() -> None:
    """Test summarize_clean_air generates driver summary with Bayesian shrinkage."""
    candidates = pd.DataFrame(
        {
            "driver": ["VER"] * 5 + ["HAM"] * 5,
            "stint": [1] * 10,
            "compound": ["MEDIUM"] * 10,
            "lap_number": list(range(1, 6)) + list(range(1, 6)),
            "tyre_life": list(range(1, 6)) + list(range(1, 6)),
            "stint_index": list(range(1, 6)) + list(range(1, 6)),
            "lap_seconds": [
                90.0,
                90.1,
                90.2,
                90.1,
                90.0,
                90.5,
                90.6,
                90.4,
                90.5,
                90.6,
            ],
            "ahead_margin_s": [5.0] * 10,
            "nearest_margin_s": [3.0] * 10,
            "clean_air": [True] * 10,
        }
    )
    priors = {"VER": (0.0, 0.8), "HAM": (0.5, 0.7)}
    summary = summarize_clean_air(candidates, priors)

    assert not summary.empty
    assert "driver" in summary.columns
    assert "model_clean_air_delta_s" in summary.columns
    assert len(summary) == 2
