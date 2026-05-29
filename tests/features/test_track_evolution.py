import pandas as pd

from f1_predictions.features.track_evolution import add_track_evolution_factor


def test_add_track_evolution_factor_basic() -> None:
    # Need at least window+1 laps for diff to be non-zero
    df = pd.DataFrame(
        {
            "LapNumber": [1, 2, 3, 4, 5, 6],
            "LapTime_s": [90.0, 89.5, 89.2, 89.8, 88.5, 87.0],
        }
    )
    result = add_track_evolution_factor(df, window=2)
    assert "Track_Evolution_Factor" in result.columns
    # Factor should be negative (improvement) for the last lap
    assert result.iloc[-1]["Track_Evolution_Factor"] < 0


def test_add_track_evolution_factor_missing_cols() -> None:
    df = pd.DataFrame({"A": [1, 2]})
    result = add_track_evolution_factor(df)
    assert "Track_Evolution_Factor" in result.columns
    assert (result["Track_Evolution_Factor"] == 0.0).all()
