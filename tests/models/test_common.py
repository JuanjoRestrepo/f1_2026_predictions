"""Tests for shared model utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from f1_predictions.models.common import (
    RegressionMetrics,
    align_feature_columns,
    chronological_split,
    evaluate_regression,
    prepare_feature_matrix,
)


def test_prepare_feature_matrix_filters_non_numeric_columns() -> None:
    """prepare_feature_matrix keeps numeric features and target only."""

    df = pd.DataFrame(
        {
            "Season": [2023, 2023, 2024],
            "LapTime_s": [90.0, 91.0, 92.0],
            "LapNumber": [1, 2, 3],
            "TyreLife": [1.0, 2.0, 3.0],
            "Driver": ["VER", "VER", "VER"],
            "Team": ["Red Bull", "Red Bull", "Red Bull"],
        }
    )

    x, y = prepare_feature_matrix(df)

    assert list(x.columns) == ["Season", "LapNumber", "TyreLife"]
    assert list(y) == [90.0, 91.0, 92.0]


def test_prepare_feature_matrix_without_target() -> None:
    """prepare_feature_matrix supports inference frames without a target."""

    df = pd.DataFrame(
        {
            "Season": [2024],
            "LapNumber": [4],
            "TyreLife": [7.0],
            "Driver": ["VER"],
        }
    )

    x, y = prepare_feature_matrix(df, require_target=False)

    assert list(x.columns) == ["Season", "LapNumber", "TyreLife"]
    assert len(y) == 0


def test_chronological_split_returns_expected_subsets() -> None:
    """chronological_split separates the requested seasons."""

    df = pd.DataFrame(
        {
            "Season": [2023, 2023, 2024, 2025],
            "LapTime_s": [90.0, 91.0, 92.0, 93.0],
        }
    )

    train_df, test_df = chronological_split(df, [2023, 2024], 2025)

    assert list(train_df["Season"]) == [2023, 2023, 2024]
    assert list(test_df["Season"]) == [2025]


def test_align_feature_columns_uses_shared_order() -> None:
    """align_feature_columns preserves the training column order."""

    x_train = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
    x_test = pd.DataFrame({"b": [7, 8], "c": [9, 10], "d": [11, 12]})

    aligned_train, aligned_test, shared_cols = align_feature_columns(x_train, x_test)

    assert shared_cols == ["b", "c"]
    assert list(aligned_train.columns) == ["b", "c"]
    assert list(aligned_test.columns) == ["b", "c"]


def test_align_feature_columns_raises_on_no_overlap() -> None:
    """align_feature_columns rejects matrices with no common features."""

    x_train = pd.DataFrame({"a": [1, 2]})
    x_test = pd.DataFrame({"b": [3, 4]})

    with pytest.raises(ValueError, match="no columns in common"):
        align_feature_columns(x_train, x_test)


def test_evaluate_regression_returns_dataclass() -> None:
    """evaluate_regression computes MAE and RMSE consistently."""

    metrics = evaluate_regression(
        np.array([1.0, 2.0, 3.0]),
        np.array([1.5, 2.0, 2.5]),
    )

    assert isinstance(metrics, RegressionMetrics)
    assert metrics.mae == pytest.approx(0.3333333, rel=1e-6)
    assert metrics.rmse == pytest.approx(0.4082482, rel=1e-6)
