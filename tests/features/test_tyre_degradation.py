import pandas as pd
import numpy as np
import pytest
from f1_predictions.features.tyre_degradation import add_tyre_degradation_slope, add_normalised_tyre_life

def test_tyre_degradation_slope_calculation():
    """Verify that OLS slope is calculated correctly."""
    # y = 0.5x + 90
    # x: [1, 2, 3] -> y: [90.5, 91.0, 91.5]
    data = {
        "Driver": ["VER"] * 3,
        "Stint": [1] * 3,
        "TyreLife": [1.0, 2.0, 3.0],
        "LapTime_s": [90.5, 91.0, 91.5]
    }
    df = pd.DataFrame(data)
    
    result = add_tyre_degradation_slope(df)
    
    assert "tyre_deg_slope" in result.columns
    # Check that slope is 0.5 for all rows in the group
    np.testing.assert_allclose(result["tyre_deg_slope"], 0.5)

def test_tyre_degradation_slope_min_laps():
    """Verify that stints with only 1 lap get NaN slope."""
    data = {
        "Driver": ["VER"],
        "Stint": [1],
        "TyreLife": [1.0],
        "LapTime_s": [90.0]
    }
    df = pd.DataFrame(data)
    
    result = add_tyre_degradation_slope(df)
    assert np.isnan(result.iloc[0]["tyre_deg_slope"])

def test_tyre_degradation_slope_collinearity():
    """Verify handling of constant TyreLife (sensor issue)."""
    data = {
        "Driver": ["VER"] * 3,
        "Stint": [1] * 3,
        "TyreLife": [1.0, 1.0, 1.0],
        "LapTime_s": [90.0, 91.0, 92.0]
    }
    df = pd.DataFrame(data)
    
    result = add_tyre_degradation_slope(df)
    assert np.isnan(result.iloc[0]["tyre_deg_slope"])

def test_normalised_tyre_life():
    """Verify min-max normalization of TyreLife."""
    data = {
        "Driver": ["VER"] * 3,
        "Stint": [1] * 3,
        "TyreLife": [10.0, 15.0, 20.0]
    }
    df = pd.DataFrame(data)
    
    result = add_normalised_tyre_life(df)
    
    assert "tyre_life_norm" in result.columns
    # 10 -> 0.0, 15 -> 0.5, 20 -> 1.0
    expected = [0.0, 0.5, 1.0]
    np.testing.assert_allclose(result["tyre_life_norm"], expected)

def test_normalised_tyre_life_single_value():
    """Verify normalization when TyreLife is constant."""
    data = {
        "Driver": ["VER"] * 2,
        "Stint": [1] * 2,
        "TyreLife": [10.0, 10.0]
    }
    df = pd.DataFrame(data)
    
    result = add_normalised_tyre_life(df)
    # Should be 0.0 as per implementation
    np.testing.assert_allclose(result["tyre_life_norm"], [0.0, 0.0])
