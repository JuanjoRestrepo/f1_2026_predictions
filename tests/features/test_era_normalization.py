import pandas as pd

from f1_predictions.features.era_normalization import apply_2026_regulations_penalty


def test_apply_2026_regulations_penalty_basic() -> None:
    df = pd.DataFrame(
        {
            "Season": [2024, 2026],
            "LapTime_s": [80.0, 80.0],
            "DownforceLevel_val": [5.0, 5.0],
        }
    )
    result = apply_2026_regulations_penalty(df)

    # 2024 should be penalized: 1.5 + (5 * 0.2) = 2.5s
    assert result.iloc[0]["LapTime_s"] == 82.5
    # 2026 should remain unchanged
    assert result.iloc[1]["LapTime_s"] == 80.0


def test_apply_2026_regulations_penalty_missing_cols() -> None:
    df = pd.DataFrame({"A": [1, 2]})
    result = apply_2026_regulations_penalty(df)
    assert "A" in result.columns
    assert len(result.columns) == 1
