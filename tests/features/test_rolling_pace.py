import numpy as np
import pandas as pd
import pytest

from f1_predictions.features.rolling_pace import (
    add_lap_delta_to_fastest,
    add_rolling_pace_features,
)


def test_rolling_pace_basic_calculation() -> None:
    """Verify that rolling mean is calculated correctly for a single driver stint."""
    data = {
        "Driver": ["VER"] * 5,
        "Stint": [1] * 5,
        "LapNumber": [1, 2, 3, 4, 5],
        "LapTime_s": [90.0, 91.0, 92.0, 93.0, 94.0],
    }
    df = pd.DataFrame(data)

    # window_short=3, window_long=5
    result = add_rolling_pace_features(df, window_short=3, window_long=5)

    # Check column existence
    assert "roll_laptime_3" in result.columns
    assert "roll_laptime_5" in result.columns
    assert "roll_std_3" in result.columns

    # Verification of values (min_periods=1)
    # Lap 1: mean of [90] = 90
    assert result.iloc[0]["roll_laptime_3"] == 90.0
    # Lap 2: mean of [90, 91] = 90.5
    assert result.iloc[1]["roll_laptime_3"] == 90.5
    # Lap 3: mean of [90, 91, 92] = 91.0
    assert result.iloc[2]["roll_laptime_3"] == 91.0
    # Lap 4: mean of [91, 92, 93] = 92.0
    assert result.iloc[3]["roll_laptime_3"] == 92.0


def test_rolling_pace_stint_isolation() -> None:
    """Verify that pace calculations do not bleed across different stints."""
    data = {
        "Driver": ["VER"] * 4,
        "Stint": [1, 1, 2, 2],
        "LapNumber": [1, 2, 3, 4],
        "LapTime_s": [90.0, 91.0, 100.0, 101.0],
    }
    df = pd.DataFrame(data)

    result = add_rolling_pace_features(df, window_short=3)

    # Lap 3 is start of Stint 2. Pace should reset to 100.0, not include Stint 1.
    # If it bled, it would be (90+91+100)/3 = 93.66
    assert result.iloc[2]["roll_laptime_3"] == 100.0
    assert result.iloc[3]["roll_laptime_3"] == 100.5


def test_rolling_pace_empty_input() -> None:
    """Test behavior with empty DataFrame."""
    df = pd.DataFrame(columns=["Driver", "Stint", "LapNumber", "LapTime_s"])
    result = add_rolling_pace_features(df)
    assert result.empty
    assert "roll_laptime_3" in result.columns


def test_rolling_pace_sorting_handled() -> None:
    """Verify that the function handles unsorted input correctly."""
    data = {
        "Driver": ["VER"] * 3,
        "Stint": [1] * 3,
        "LapNumber": [3, 1, 2],
        "LapTime_s": [92.0, 90.0, 91.0],
    }
    df = pd.DataFrame(data)

    result = add_rolling_pace_features(df, window_short=3)

    # Function should sort by LapNumber internally (or as part of contract)
    # After sorting: [1:90, 2:91, 3:92]
    # Lap 1 (index 1 in original) -> 90.0
    # Lap 2 (index 2 in original) -> 90.5
    # Lap 3 (index 0 in original) -> 91.0
    assert result.loc[1, "roll_laptime_3"] == 90.0
    assert result.loc[2, "roll_laptime_3"] == 90.5
    assert result.loc[0, "roll_laptime_3"] == 91.0


def test_rolling_pace_errors() -> None:
    """Verify that type and key errors are raised correctly."""
    # Non-DataFrame input — raw string avoids RUF043 metacharacter warning
    with pytest.raises(TypeError, match=r"Expected pd\.DataFrame"):
        add_rolling_pace_features(["not", "a", "df"])

    # Missing columns
    df = pd.DataFrame({"Driver": ["VER"], "Stint": [1]})
    with pytest.raises(KeyError, match=r"Required column\(s\) missing"):
        add_rolling_pace_features(df)


def test_delta_to_fastest() -> None:
    """Verify the delta_to_fastest_s feature calculation."""
    data = {
        "Driver": ["VER"] * 3,
        "Stint": [1] * 3,
        "LapTime_s": [90.0, 92.0, 91.0],
    }
    df = pd.DataFrame(data)
    result = add_lap_delta_to_fastest(df, group_cols=["Driver", "Stint"])

    # Fastest is 90.0
    # 90-90=0, 92-90=2, 91-90=1
    np.testing.assert_allclose(result["delta_to_fastest_s"], [0.0, 2.0, 1.0])
