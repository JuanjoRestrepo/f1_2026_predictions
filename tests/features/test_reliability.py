import pandas as pd

from f1_predictions.features.reliability import (
    add_brake_wear_proxy,
    add_pu_strain_index,
)


def test_add_brake_wear_proxy_basic() -> None:
    df = pd.DataFrame(
        {
            "Driver": ["VER", "VER", "VER", "HAM", "HAM"],
            "LapNumber": [1, 2, 3, 1, 2],
            "Sector3Time_s": [20.0, 20.5, 20.2, 21.0, 21.5],
        }
    )
    result = add_brake_wear_proxy(df, window=2)
    assert "Brake_Wear_Proxy" in result.columns
    # Check that variance is calculated
    # (first lap of each driver should be 0 or NaN filled with 0)
    assert result.iloc[0]["Brake_Wear_Proxy"] == 0.0
    assert result.iloc[1]["Brake_Wear_Proxy"] > 0.0


def test_add_brake_wear_proxy_missing_cols() -> None:
    df = pd.DataFrame({"A": [1, 2]})
    result = add_brake_wear_proxy(df)
    assert "Brake_Wear_Proxy" in result.columns
    assert (result["Brake_Wear_Proxy"] == 0.0).all()


def test_add_pu_strain_index_basic() -> None:
    df = pd.DataFrame({"LapNumber": [1, 10, 20], "TrackTemp": [20.0, 30.0, 40.0]})
    result = add_pu_strain_index(df)
    assert "PU_Strain_Index" in result.columns
    # At 30C, multiplier is 1.0, so Index == LapNumber
    assert result.iloc[1]["PU_Strain_Index"] == 10.0
    # At 40C, multiplier is 40/30 > 1.0
    assert result.iloc[2]["PU_Strain_Index"] > 20.0
    # At 20C, multiplier is 20/30 < 1.0
    assert result.iloc[0]["PU_Strain_Index"] < 1.0


def test_add_pu_strain_index_no_temp() -> None:
    df = pd.DataFrame({"LapNumber": [1, 2, 3]})
    result = add_pu_strain_index(df)
    assert "PU_Strain_Index" in result.columns
    assert (result["PU_Strain_Index"] == result["LapNumber"]).all()
