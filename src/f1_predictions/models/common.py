"""Shared utilities for F1 regression model training and evaluation.

These helpers centralise the data preparation and metric calculation logic
used by the XGBoost and LightGBM model wrappers. That keeps the model classes
thin and ensures both models are benchmarked on the exact same feature matrix
and chronological split.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error  # type: ignore[import-untyped]

DEFAULT_TARGET_COLUMN: str = "LapTime_s"
DEFAULT_SEASON_COLUMN: str = "Season"

# Identifiers, raw categoricals, and target-like columns that should never be
# passed directly into tree-based regressors.
DEFAULT_DROP_COLS: list[str] = [
    "Driver",
    "Team",
    "EventName",
    "SessionType",
    "Time",
    "LapTime",
    "LapTime_s",
    "delta_to_fastest_s",
    "PitOutTime",
    "PitInTime",
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    "Compound",
]


@dataclass(frozen=True, slots=True)
class RegressionMetrics:
    """Regression metrics used to compare tree-based pace models.

    Attributes:
        mae: Mean absolute error in seconds.
        rmse: Root mean squared error in seconds.
    """

    mae: float
    rmse: float

    def as_dict(self) -> dict[str, float]:
        """Convert the metrics into the notebook-friendly dict shape."""
        return {"MAE": self.mae, "RMSE": self.rmse}


def prepare_feature_matrix(
    df: pd.DataFrame,
    target_column: str = DEFAULT_TARGET_COLUMN,
    drop_cols: Sequence[str] = DEFAULT_DROP_COLS,
    require_target: bool = True,
) -> tuple[pd.DataFrame, pd.Series]:
    """Build a numeric feature matrix and target vector from a Gold DataFrame.

    Args:
        df: Gold-layer DataFrame containing the engineered features.
        target_column: Name of the regression target column.
        drop_cols: Columns to exclude before selecting numeric dtypes.
        require_target: If ``True``, raise when the target column is missing.
            If ``False``, return an empty target Series for inference use.

    Returns:
        Tuple of ``(X, y)`` where ``X`` contains only numeric model features
        and ``y`` contains the target values when available.

    Raises:
        KeyError: If ``require_target`` is ``True`` and the target is missing.
        ValueError: If the requested target column exists but only contains
            missing values after cleaning.
    """
    if require_target:
        if target_column not in df.columns:
            msg = f"Target column '{target_column}' not found in DataFrame."
            raise KeyError(msg)
        clean_df = df.dropna(subset=[target_column]).copy()
        if clean_df.empty:
            msg = "No rows remain after dropping missing target values."
            raise ValueError(msg)
        y = clean_df[target_column].copy()
    else:
        clean_df = df.copy()
        if target_column in clean_df.columns:
            clean_df = clean_df.drop(columns=[target_column])
        y = pd.Series(dtype="float64", name=target_column)

    cols_to_drop = [col for col in drop_cols if col in clean_df.columns]
    x = clean_df.drop(columns=cols_to_drop, errors="ignore")
    
    # Ensure only pure numeric features are passed to the model.
    # We explicitly exclude timedeltas and datetimes which can sometimes 
    # be caught in np.number but are not supported by GBMs.
    x = x.select_dtypes(include=[np.number])
    x = x.select_dtypes(exclude=["timedelta", "datetime"])

    return x, y


def chronological_split(
    df: pd.DataFrame,
    train_years: Sequence[int],
    test_year: int,
    season_column: str = DEFAULT_SEASON_COLUMN,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a multi-season DataFrame into train and test subsets.

    Args:
        df: Full multi-season DataFrame.
        train_years: Seasons to use for training.
        test_year: Season to reserve for testing.
        season_column: Column containing the season year.

    Returns:
        ``(train_df, test_df)``.

    Raises:
        KeyError: If ``season_column`` is missing.
        ValueError: If either split is empty.
    """
    if season_column not in df.columns:
        msg = f"Required season column '{season_column}' not found."
        raise KeyError(msg)

    train_mask = df[season_column].isin(train_years)
    test_mask = df[season_column] == test_year

    train_df = df[train_mask].copy()
    test_df = df[test_mask].copy()

    if train_df.empty:
        msg = f"No training rows found for years {list(train_years)}."
        raise ValueError(msg)
    if test_df.empty:
        msg = f"No test rows found for year {test_year}."
        raise ValueError(msg)

    return train_df, test_df


def align_feature_columns(
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Align train and test matrices to the shared feature columns.

    The notebook currently constructs Gold-layer files session-by-session, so
    one-hot encoded categorical columns may differ across sessions. Intersecting
    the column sets keeps the benchmark fair and prevents model failures caused
    by session-specific feature drift.

    Args:
        x_train: Training feature matrix.
        x_test: Test feature matrix.

    Returns:
        Tuple of aligned train matrix, aligned test matrix, and the ordered
        shared column list.

    Raises:
        ValueError: If the matrices have no columns in common.
    """
    shared_cols = [col for col in x_train.columns if col in x_test.columns]
    if not shared_cols:
        msg = "Train and test feature matrices have no columns in common."
        raise ValueError(msg)

    return x_train[shared_cols], x_test[shared_cols], shared_cols


def evaluate_regression(
    y_true: pd.Series | np.ndarray,
    y_pred: np.ndarray,
) -> RegressionMetrics:
    """Calculate MAE and RMSE for regression predictions."""
    mae = mean_absolute_error(y_true, y_pred)
    rmse = root_mean_squared_error(y_true, y_pred)
    return RegressionMetrics(mae=mae, rmse=rmse)
