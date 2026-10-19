"""Pandas-side preparation for the shared local/cloud feature contract.

Separated from :mod:`f1_predictions.features.contract` so the contract module
stays dependency-free and can be imported by the Databricks DLT pipeline. This
module is the only place that decides how missing feature values are treated:

* ``aggregate`` keeps the historical ``fillna(0.0)`` behaviour;
* ``lap`` leaves NaN intact, because a rolling mean with no prior laps is
  missing information — zero-filling it would tell XGBoost the driver's last
  three laps averaged 0 seconds.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from f1_predictions.features.contract import (
    VERSION_COLUMN,
    TrainingSchema,
    validate_feature_frame,
)
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class TrainingData:
    """A validated model matrix and its aligned target/group columns.

    Attributes:
        X: Feature matrix in ``schema.features`` order.
        y: Target aligned to ``X``.
        groups: CV group labels aligned to ``X``, or ``None`` for the legacy
            aggregate split.
        dropped_target_rows: Rows removed because the target was missing.
    """

    X: pd.DataFrame
    y: pd.Series
    groups: pd.Series | None
    dropped_target_rows: int


def _assert_contract_version(df: pd.DataFrame, schema: TrainingSchema) -> None:
    """Reject a table stamped with a different feature-contract version."""
    if schema.contract_version is None:
        return

    versions = set(df[VERSION_COLUMN].dropna().unique().tolist())
    expected = {schema.contract_version}
    if versions != expected:
        msg = (
            f"Table '{schema.table}' carries {VERSION_COLUMN}={sorted(versions)}, "
            f"but the code expects {schema.contract_version}. Deploy/refresh the "
            "DLT pipeline before training on this table."
        )
        raise ValueError(msg)


def _assert_numeric_features(matrix: pd.DataFrame, schema: TrainingSchema) -> None:
    """Reject non-numeric feature columns before XGBoost sees an object dtype."""
    non_numeric = [
        column
        for column in schema.features
        if not pd.api.types.is_numeric_dtype(matrix[column])
    ]
    if non_numeric:
        msg = (
            f"{schema.name} feature matrix contains non-numeric column(s): "
            f"{non_numeric}. The Gold table must emit numeric features."
        )
        raise ValueError(msg)


def prepare_feature_frame(
    df: pd.DataFrame,
    schema: TrainingSchema,
) -> pd.DataFrame:
    """Validate and select the feature matrix for batch scoring.

    The target is optional here: a live/prediction table may not carry it.

    Args:
        df: Gold rows, normally ``spark.table(...).toPandas()``.
        schema: Selected training schema.

    Returns:
        A float64 feature matrix in contract order.

    Raises:
        ValueError: If the frame is empty, misses a required column, carries
            the wrong contract version, or has a non-numeric feature.
    """
    validate_feature_frame(df, schema, require_target=False, require_version=True)

    if df.empty:
        msg = f"Table '{schema.table}' returned no rows to score."
        raise ValueError(msg)

    _assert_contract_version(df, schema)

    matrix = df.loc[:, list(schema.features)].copy()
    if schema.fill_missing_features:
        matrix = matrix.fillna(0.0)
    _assert_numeric_features(matrix, schema)
    return matrix.astype("float64")


def prepare_training_data(
    df: pd.DataFrame,
    schema: TrainingSchema,
) -> TrainingData:
    """Validate a Gold frame and build the aligned training matrix.

    Args:
        df: Gold rows, normally ``spark.table(...).toPandas()``.
        schema: Selected training schema.

    Returns:
        Training matrix, target, optional CV groups and the number of rows
        dropped for a missing target.

    Raises:
        ValueError: If the frame is empty, misses a required column, carries
            the wrong contract version, has a non-numeric feature, or has no
            rows with a target.
    """
    validate_feature_frame(df, schema, require_target=True, require_version=True)

    if df.empty:
        msg = f"Table '{schema.table}' returned no rows to train on."
        raise ValueError(msg)

    _assert_contract_version(df, schema)

    y = df[schema.target]
    mask = y.notna()
    dropped = int((~mask).sum())
    if not mask.any():
        msg = f"Table '{schema.table}' has no non-null '{schema.target}' rows."
        raise ValueError(msg)

    matrix = df.loc[mask, list(schema.features)].copy()
    if schema.fill_missing_features:
        matrix = matrix.fillna(0.0)
    _assert_numeric_features(matrix, schema)
    matrix = matrix.astype("float64")

    groups: pd.Series | None = None
    if schema.cv_group_columns:
        group_frame = df.loc[mask, list(schema.cv_group_columns)]
        groups = group_frame.astype(str).agg("|".join, axis=1)

    if dropped:
        logger.warning(
            "Dropped %d row(s) from '%s' with a null '%s'.",
            dropped,
            schema.table,
            schema.target,
        )

    return TrainingData(
        X=matrix,
        y=y.loc[mask],
        groups=groups,
        dropped_target_rows=dropped,
    )


def build_prediction_frame(
    df: pd.DataFrame,
    predictions: Sequence[float] | pd.Series | np.ndarray,
    schema: TrainingSchema,
    *,
    model_name: str,
    scored_at_utc: datetime | None = None,
) -> pd.DataFrame:
    """Attach predictions to row keys for writing a Delta prediction table.

    Args:
        df: Scored Gold rows (used for the schema's key columns).
        predictions: One prediction per row, in the same order as ``df``.
        schema: Selected training schema.
        model_name: Registered model name stamped on every output row.
        scored_at_utc: Scoring timestamp; defaults to the current UTC time.

    Returns:
        A frame with ``schema.keys``, ``prediction``, ``model_name`` and
        ``scored_at_utc``.

    Raises:
        ValueError: If the prediction count does not match the row count.
    """
    values = np.asarray(predictions, dtype=float).reshape(-1)
    if len(values) != len(df):
        msg = (
            f"Received {len(values)} prediction(s) for {len(df)} row(s) from "
            f"'{schema.table}'."
        )
        raise ValueError(msg)

    out: pd.DataFrame = df.loc[:, list(schema.keys)].reset_index(drop=True).copy()
    out["prediction"] = values
    out["model_name"] = model_name
    out["scored_at_utc"] = (scored_at_utc or datetime.now(UTC)).isoformat()
    return out
