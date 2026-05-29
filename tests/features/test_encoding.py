import numpy as np
import pandas as pd
import pytest

from f1_predictions.features.encoding import (
    CategoricalFeatureEncoder,
    add_grid_position_features,
)


def test_grid_position_features() -> None:
    """Verify binary flags and gap for grid positions."""
    data = {"GridPosition": [1.0, 2.0, 10.0, 11.0, np.nan]}
    df = pd.DataFrame(data)

    result = add_grid_position_features(df)

    # Front row: 1, 2 -> 1; others -> 0
    assert result.iloc[0]["grid_front_row"] == 1
    assert result.iloc[1]["grid_front_row"] == 1
    assert result.iloc[2]["grid_front_row"] == 0

    # Top 10: 1, 2, 10 -> 1; 11 -> 0
    assert result.iloc[0]["grid_top10"] == 1
    assert result.iloc[1]["grid_top10"] == 1
    assert result.iloc[2]["grid_top10"] == 1
    assert result.iloc[3]["grid_top10"] == 0

    # Gap: pos - 1
    assert result.iloc[0]["grid_position_gap"] == 0.0
    assert result.iloc[1]["grid_position_gap"] == 1.0
    assert result.iloc[3]["grid_position_gap"] == 10.0

    # NaNs should propagate
    assert pd.isna(result.iloc[4]["grid_front_row"])
    assert pd.isna(result.iloc[4]["grid_position_gap"])


def test_categorical_feature_encoder_basic() -> None:
    """Verify OHE fit and transform consistency."""
    train_data = {
        "Compound": ["SOFT", "MEDIUM", "HARD"],
        "Team": ["Red Bull", "Mercedes", "Ferrari"],
        "Other": [1, 2, 3],
    }
    train_df = pd.DataFrame(train_data)

    encoder = CategoricalFeatureEncoder(columns=["Compound", "Team"])
    encoded_train = encoder.fit_transform(train_df)

    # Original columns are preserved for reporting/EDA and appended OHE columns
    assert "Compound" in encoded_train.columns
    assert "Team" in encoded_train.columns
    assert "Other" in encoded_train.columns

    # Check for OHE columns
    assert "Compound_SOFT" in encoded_train.columns
    assert "Team_Red Bull" in encoded_train.columns

    # Test transform on new data
    test_data = {"Compound": ["SOFT"], "Team": ["Red Bull"], "Other": [4]}
    test_df = pd.DataFrame(test_data)
    encoded_test = encoder.transform(test_df)

    assert encoded_test.iloc[0]["Compound_SOFT"] == 1.0
    assert encoded_test.iloc[0]["Compound_MEDIUM"] == 0.0


def test_categorical_feature_encoder_unknown_category() -> None:
    """Verify handle_unknown='ignore' behavior."""
    train_df = pd.DataFrame({"Cat": ["A", "B"]})
    encoder = CategoricalFeatureEncoder(columns=["Cat"])
    encoder.fit(train_df)

    # New category "C" should result in zeros for all OHE columns
    test_df = pd.DataFrame({"Cat": ["C"]})
    encoded_test = encoder.transform(test_df)

    assert encoded_test["Cat_A"].iloc[0] == 0.0
    assert encoded_test["Cat_B"].iloc[0] == 0.0


def test_categorical_feature_encoder_unfitted_raises() -> None:
    """Verify error when transforming before fitting."""
    encoder = CategoricalFeatureEncoder(columns=["Cat"])
    with pytest.raises(RuntimeError, match="must be fitted before transform"):
        encoder.transform(pd.DataFrame({"Cat": ["A"]}))
