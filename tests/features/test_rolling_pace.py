"""Tests for rolling pace features — causal (t-1) boundary contract.

All rolling and delta features now enforce a strict pre-lap causal boundary:
each lap's feature value reflects only completed *prior* laps, never the lap
being predicted. This prevents target leakage in chronological cross-validation.

Key behavioural contracts:
- Lap 1 in each (Driver, Stint) group returns NaN for rolling features.
- The second lap returns the single prior lap's value (min_periods=1 on shifted
  series), not the average of two.
- ``delta_to_fastest_s`` uses the cumulative minimum of prior laps; the first
  lap always returns NaN, and a new personal-best lap registers delta=0 only
  from the *following* lap onward.
"""

import numpy as np
import pandas as pd
import pytest

from f1_predictions.features.rolling_pace import (
    add_lap_delta_to_fastest,
    add_rolling_pace_features,
)


def test_rolling_pace_basic_calculation() -> None:
    """Causal rolling mean: each lap's feature reflects only prior laps.

    Data: VER, Stint 1, LapTimes = [90, 91, 92, 93, 94]

    After shift(1):         [NaN, 90, 91, 92, 93]
    Rolling(3, min_periods=1):
      Lap 1: mean([]) → NaN  (shift produces NaN, window sees only NaN)
      Lap 2: mean([90]) = 90.0       (one prior lap)
      Lap 3: mean([90, 91]) = 90.5   (two prior laps)
      Lap 4: mean([90, 91, 92]) = 91.0  (full window)
      Lap 5: mean([91, 92, 93]) = 92.0  (rolling, drops oldest)
    """
    data = {
        "Driver": ["VER"] * 5,
        "Stint": [1] * 5,
        "LapNumber": [1, 2, 3, 4, 5],
        "LapTime_s": [90.0, 91.0, 92.0, 93.0, 94.0],
    }
    df = pd.DataFrame(data)

    result = add_rolling_pace_features(df, window_short=3, window_long=5)

    # Column existence
    assert "roll_laptime_3" in result.columns
    assert "roll_laptime_5" in result.columns
    assert "roll_std_3" in result.columns

    # Sort result by LapNumber for positional access
    result = result.sort_values("LapNumber").reset_index(drop=True)

    # Lap 1: no prior laps → NaN
    assert np.isnan(result.iloc[0]["roll_laptime_3"])
    # Lap 2: mean of [90] = 90.0
    assert result.iloc[1]["roll_laptime_3"] == pytest.approx(90.0)
    # Lap 3: mean of [90, 91] = 90.5
    assert result.iloc[2]["roll_laptime_3"] == pytest.approx(90.5)
    # Lap 4: mean of [90, 91, 92] = 91.0  (full window)
    assert result.iloc[3]["roll_laptime_3"] == pytest.approx(91.0)
    # Lap 5: rolling drops lap-1, mean of [91, 92, 93] = 92.0
    assert result.iloc[4]["roll_laptime_3"] == pytest.approx(92.0)


def test_rolling_pace_stint_isolation() -> None:
    """Rolling window resets at stint boundaries; no cross-stint bleed."""
    data = {
        "Driver": ["VER"] * 4,
        "Stint": [1, 1, 2, 2],
        "LapNumber": [1, 2, 3, 4],
        "LapTime_s": [90.0, 91.0, 100.0, 101.0],
    }
    df = pd.DataFrame(data)

    result = add_rolling_pace_features(df, window_short=3)
    result = result.sort_values("LapNumber").reset_index(drop=True)

    # Stint 1, Lap 1 → NaN (first lap, no prior)
    assert np.isnan(result.iloc[0]["roll_laptime_3"])
    # Stint 1, Lap 2 → mean([90]) = 90.0 (causal: only lap-1 prior)
    assert result.iloc[1]["roll_laptime_3"] == pytest.approx(90.0)
    # Stint 2, Lap 3 → NaN (first lap of this stint, group resets)
    assert np.isnan(result.iloc[2]["roll_laptime_3"])
    # Stint 2, Lap 4 → mean([100]) = 100.0 (only lap-3 prior within stint)
    assert result.iloc[3]["roll_laptime_3"] == pytest.approx(100.0)


def test_rolling_pace_empty_input() -> None:
    """Empty DataFrame returns empty result with correct column schema."""
    df = pd.DataFrame(columns=["Driver", "Stint", "LapNumber", "LapTime_s"])
    result = add_rolling_pace_features(df)
    assert result.empty
    assert "roll_laptime_3" in result.columns


def test_rolling_pace_sorting_handled() -> None:
    """Function sorts by LapNumber internally; result indexed to original index."""
    data = {
        "Driver": ["VER"] * 3,
        "Stint": [1] * 3,
        "LapNumber": [3, 1, 2],
        "LapTime_s": [92.0, 90.0, 91.0],
    }
    df = pd.DataFrame(data)

    result = add_rolling_pace_features(df, window_short=3)
    result = result.sort_values("LapNumber").reset_index(drop=True)

    # Sorted by LapNumber: [1:90, 2:91, 3:92]
    # Causal rolling: [NaN, 90.0, mean(90,91)=90.5]
    assert np.isnan(result.iloc[0]["roll_laptime_3"])
    assert result.iloc[1]["roll_laptime_3"] == pytest.approx(90.0)
    assert result.iloc[2]["roll_laptime_3"] == pytest.approx(90.5)


def test_rolling_pace_errors() -> None:
    """Type and key errors are raised with informative messages."""
    with pytest.raises(TypeError, match=r"Expected pd\.DataFrame"):
        add_rolling_pace_features(["not", "a", "df"])  # type: ignore[arg-type]

    df = pd.DataFrame({"Driver": ["VER"], "Stint": [1]})
    with pytest.raises(KeyError, match=r"Required column\(s\) missing"):
        add_rolling_pace_features(df)


def test_delta_to_fastest_causal() -> None:
    """delta_to_fastest_s reflects the best *prior* lap, not the session minimum.

    Data: VER, 3 laps → [90.0, 92.0, 91.0]
    LapNumbers: [1, 2, 3]

    Causal expanding cummin on shifted series:
      Lap 1: shift(1)=NaN  → prior_best=NaN → delta=NaN
      Lap 2: shift(1)=90   → prior_best=90  → delta=92-90=2.0
      Lap 3: shift(1)=92   → prior_best=min(90,92)=90 → delta=91-90=1.0

    Note: Lap 1 returns NaN (no prior lap), whereas the old non-causal
    implementation returned 0.0 (90-min(90,92,91)=0).
    """
    data = {
        "Driver": ["VER"] * 3,
        "EventName": ["Monaco Grand Prix"] * 3,
        "LapNumber": [1, 2, 3],
        "LapTime_s": [90.0, 92.0, 91.0],
    }
    df = pd.DataFrame(data)
    result = add_lap_delta_to_fastest(df)
    result = result.sort_values("LapNumber").reset_index(drop=True)

    assert np.isnan(result.iloc[0]["delta_to_fastest_s"])
    assert result.iloc[1]["delta_to_fastest_s"] == pytest.approx(2.0)
    assert result.iloc[2]["delta_to_fastest_s"] == pytest.approx(1.0)


def test_delta_to_fastest_new_best_is_registered_next_lap() -> None:
    """A driver who sets a new fastest lap registers delta=0 from the *next* lap.

    Data: VER, 4 laps → [92.0, 91.0, 90.0, 93.0]
    LapNumbers: [1, 2, 3, 4]

    Causal cummin (prior only):
      Lap 1: NaN
      Lap 2: delta=91-92= -1.0  (faster than the one prior lap)
      Lap 3: delta=90-min(92,91)=90-91= -1.0 (new best, but vs min of laps 1-2)
      Lap 4: delta=93-min(92,91,90)=93-90=3.0
    """
    data = {
        "Driver": ["VER"] * 4,
        "EventName": ["Monaco Grand Prix"] * 4,
        "LapNumber": [1, 2, 3, 4],
        "LapTime_s": [92.0, 91.0, 90.0, 93.0],
    }
    df = pd.DataFrame(data)
    result = add_lap_delta_to_fastest(df)
    result = result.sort_values("LapNumber").reset_index(drop=True)

    assert np.isnan(result.iloc[0]["delta_to_fastest_s"])
    assert result.iloc[1]["delta_to_fastest_s"] == pytest.approx(-1.0)
    assert result.iloc[2]["delta_to_fastest_s"] == pytest.approx(-1.0)
    assert result.iloc[3]["delta_to_fastest_s"] == pytest.approx(3.0)


def test_delta_to_fastest_multi_driver_isolation() -> None:
    """delta_to_fastest_s is computed per driver, not across the whole field."""
    data = {
        "Driver": ["VER", "VER", "HAM", "HAM"],
        "EventName": ["Monaco Grand Prix"] * 4,
        "LapNumber": [1, 2, 1, 2],
        "LapTime_s": [90.0, 92.0, 95.0, 93.0],
    }
    df = pd.DataFrame(data)
    result = add_lap_delta_to_fastest(df)
    result = result.sort_values(["Driver", "LapNumber"]).reset_index(drop=True)

    # VER: Lap1=NaN, Lap2=92-90=2.0
    assert np.isnan(result[result["Driver"] == "VER"].iloc[0]["delta_to_fastest_s"])
    assert result[result["Driver"] == "VER"].iloc[1][
        "delta_to_fastest_s"
    ] == pytest.approx(2.0)
    # HAM: Lap1=NaN, Lap2=93-95=-2.0
    assert np.isnan(result[result["Driver"] == "HAM"].iloc[0]["delta_to_fastest_s"])
    assert result[result["Driver"] == "HAM"].iloc[1][
        "delta_to_fastest_s"
    ] == pytest.approx(-2.0)
