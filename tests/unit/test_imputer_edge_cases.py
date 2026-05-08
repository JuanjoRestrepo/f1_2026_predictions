"""Edge case tests for f1_predictions.cleaning.imputer.

Covers branches not reached by standard unit tests (missing columns, empty DFs,
global fallback logic).
"""

import pandas as pd

from f1_predictions.cleaning.imputer import (
    drop_null_lap_times,
    impute_speed_traps,
    impute_tyre_data,
    run_imputation_pipeline,
)


def test_drop_null_lap_times_missing_column() -> None:
    """It should return the DF unchanged if the lap time column is missing."""
    df = pd.DataFrame({"A": [1, 2]})
    result, dropped = drop_null_lap_times(df, lap_time_col="Missing")
    assert dropped == 0
    assert result.equals(df)

def test_impute_tyre_data_no_mode() -> None:
    """It should leave Compound as NaN if the group has no mode (all NaNs)."""
    df = pd.DataFrame({
        "Driver": ["VER", "VER"],
        "Stint": [1, 1],
        "Compound": [None, None]
    })
    result, audit = impute_tyre_data(df)
    assert result["Compound"].isna().all()
    assert audit.get("Compound", 0) == 0

def test_impute_speed_traps_missing_group_column() -> None:
    """It should fall back to global median if grouping columns are missing."""
    df = pd.DataFrame({
        "Driver": ["VER", "HAM", "VER"],
        "SpeedI1": [300.0, 310.0, None]
    })
    # 'EventName' is missing from the DataFrame
    result, audit = impute_speed_traps(df)
    assert result["SpeedI1"].iloc[2] == 305.0 # Global median of [300, 310]
    assert audit["SpeedI1"] == 1

def test_impute_speed_traps_residual_nulls() -> None:
    """It should fall back to global median for groups that are all NaNs."""
    df = pd.DataFrame({
        "Driver": ["VER", "VER", "HAM"],
        "EventName": ["GP1", "GP1", "GP1"],
        "SpeedI1": [None, None, 320.0]
    })
    # VER group is all NaN, HAM group has 320.
    # Global median is 320.
    result, audit = impute_speed_traps(df)
    assert result["SpeedI1"].iloc[0] == 320.0
    assert audit["SpeedI1"] == 2

def test_run_imputation_pipeline_smoke() -> None:
    """Verify that the full pipeline runs and aggregates audit."""
    df = pd.DataFrame({
        "Driver": ["VER"],
        "Stint": [1],
        "EventName": ["GP1"],
        "LapTime_s": [90.0],
        "TyreLife": [1.0],
        "Compound": ["SOFT"],
        "SpeedI1": [300.0]
    })
    result, audit = run_imputation_pipeline(df)
    assert "dropped_null_lap_times" in audit
    assert "tyre" in audit
    assert "speed_traps" in audit
    assert len(result) == 1
