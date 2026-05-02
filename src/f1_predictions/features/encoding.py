"""Categorical encoding and grid position features for the f1_predictions pipeline.

Encoding strategy rationale:

    ``Compound`` (5 categories: SOFT/MEDIUM/HARD/INTERMEDIATE/WET):
        One-hot encoded. All 5 categories are semantically distinct with
        fundamentally different performance profiles. Label encoding would
        imply an ordinal relationship that does not exist.

    ``EventName`` / Circuit (20+ circuits per season):
        One-hot encoded with ``handle_unknown="ignore"`` so that a 2026 circuit
        not seen in 2024-2025 training data maps to the all-zeros vector rather
        than raising an error. This is critical for generalisability to the 2026
        calendar which may include new venues (e.g. Madrid).

    ``Team`` (10 canonical constructors):
        One-hot encoded. Each constructor has a distinct performance envelope
        that is not captured by pace features alone (e.g., reliability, PU
        characteristics). OHE rather than target encoding to avoid data leakage
        when fitting on the training set.

    ``GridPosition``:
        Kept as a raw numeric feature (the XGBoost regressor can learn the
        non-linear relationship between grid position and finishing time
        without binning). Additionally, two derived binary features are added:
            - ``grid_front_row``  : 1 if GridPosition ∈ {1, 2}.
            - ``grid_top10``      : 1 if GridPosition ≤ 10 (Q3 qualifier).
            - ``grid_position_gap``: gap between GridPosition and pole (1).
              For the pole-sitter this is 0.

Scikit-learn's ``OneHotEncoder`` is used rather than ``pd.get_dummies()``
for three reasons:
    1. ``fit()`` / ``transform()`` separation ensures the test set is encoded
       using the training set's category vocabulary — no category leakage.
    2. ``handle_unknown="ignore"`` natively handles unseen categories.
    3. The fitted encoder is serialisable (joblib) and ships with the model
       artifact, making deployment reproducible.
"""

from __future__ import annotations

import pandas as pd
from sklearn.preprocessing import OneHotEncoder  # type: ignore[import-untyped]

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Categorical columns encoded by default. Order determines column order in output.
DEFAULT_OHE_COLUMNS: list[str] = ["Compound", "EventName", "Team"]

# Grid position threshold for binary features.
FRONT_ROW_THRESHOLD: int = 2
TOP_10_THRESHOLD: int = 10

# Output column names for grid position features.
COL_GRID_FRONT_ROW: str = "grid_front_row"
COL_GRID_TOP10: str = "grid_top10"
COL_GRID_GAP: str = "grid_position_gap"


# ── Grid position features ────────────────────────────────────────────────────

def add_grid_position_features(
    df: pd.DataFrame,
    grid_col: str = "GridPosition",
) -> pd.DataFrame:
    """Add binary and gap features derived from qualifying grid position.

    Features added:
        - ``grid_front_row``: 1 if GridPosition ≤ 2, else 0.
        - ``grid_top10``:     1 if GridPosition ≤ 10, else 0.
        - ``grid_position_gap``: GridPosition - 1 (gap to pole, 0 for pole).

    Null ``GridPosition`` values (DNS, DQ) produce NaN in all three columns.
    XGBoost handles NaN natively at split time.

    Args:
        df: Results or joined laps-results DataFrame containing ``grid_col``.
        grid_col: Column name for the qualifying grid position.

    Returns:
        New DataFrame with three grid feature columns appended.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.
        KeyError: If ``grid_col`` is absent.
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)
    if grid_col not in df.columns:
        msg = f"Column '{grid_col}' not found. Available: {list(df.columns)}"
        raise KeyError(msg)

    result = df.copy()
    gp = result[grid_col]

    result[COL_GRID_FRONT_ROW] = (gp <= FRONT_ROW_THRESHOLD).astype("Int8")
    result[COL_GRID_TOP10] = (gp <= TOP_10_THRESHOLD).astype("Int8")
    result[COL_GRID_GAP] = gp - 1.0

    logger.info(
        "Grid position features added: %s, %s, %s",
        COL_GRID_FRONT_ROW, COL_GRID_TOP10, COL_GRID_GAP,
    )
    return result


# ── OneHotEncoder wrapper ─────────────────────────────────────────────────────

class CategoricalFeatureEncoder:
    """Fit-transform wrapper for OHE of F1 categorical columns.

    Wraps ``sklearn.preprocessing.OneHotEncoder`` with:
        - pandas-aware fit/transform (returns DataFrame, not sparse matrix).
        - ``handle_unknown="ignore"`` for graceful 2026 calendar extension.
        - Serialisable state — fitted encoder persists with the model artifact.

    Usage::

        encoder = CategoricalFeatureEncoder()
        train_encoded = encoder.fit_transform(train_df)
        test_encoded  = encoder.transform(test_df)

    Attributes:
        columns: Categorical columns to encode.
        _encoder: Fitted sklearn OneHotEncoder.
        _feature_names: Output column names after fitting.
        _is_fitted: Whether ``fit()`` has been called.
    """

    def __init__(self, columns: list[str] | None = None) -> None:
        """Initialise the encoder with the columns to one-hot encode.

        Args:
            columns: Column names to OHE. Defaults to
                ``DEFAULT_OHE_COLUMNS`` when ``None``.
        """
        self.columns: list[str] = (
            columns if columns is not None else DEFAULT_OHE_COLUMNS
        )
        self._encoder: OneHotEncoder = OneHotEncoder(
            handle_unknown="ignore",
            sparse_output=False,   # Return dense array; no scipy sparse dependency
            dtype="float32",       # float32 saves memory vs float64 for OHE features
        )
        self._feature_names: list[str] = []
        self._is_fitted: bool = False

    def fit(self, df: pd.DataFrame) -> CategoricalFeatureEncoder:
        """Fit the encoder on the training DataFrame.

        Args:
            df: Training DataFrame containing ``self.columns``.

        Returns:
            ``self`` for method chaining.

        Raises:
            KeyError: If any column in ``self.columns`` is absent from ``df``.
        """
        missing = [c for c in self.columns if c not in df.columns]
        if missing:
            msg = f"OHE columns missing from DataFrame: {missing}"
            raise KeyError(msg)

        self._encoder.fit(df[self.columns].astype(str))
        self._feature_names = list(self._encoder.get_feature_names_out(self.columns))
        self._is_fitted = True

        total_features = len(self._feature_names)
        logger.info(
            "CategoricalFeatureEncoder fitted on %d column(s) → %d OHE features. "
            "Columns: %s",
            len(self.columns), total_features, self.columns,
        )
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform a DataFrame, replacing categorical cols with OHE columns.

        The original categorical columns are **dropped** and replaced by the
        OHE output. All other columns are preserved in their original order,
        with OHE columns appended at the right.

        Args:
            df: DataFrame to transform. Must have been seen by ``fit()``
                (or contain a superset of those columns).

        Returns:
            New DataFrame with OHE columns replacing the categorical originals.

        Raises:
            RuntimeError: If called before ``fit()``.
            KeyError: If any OHE column is absent from ``df``.
        """
        if not self._is_fitted:
            msg = (
                "CategoricalFeatureEncoder must be fitted before transform(). "
                "Call fit() first."
            )
            raise RuntimeError(msg)

        missing = [c for c in self.columns if c not in df.columns]
        if missing:
            msg = f"OHE columns missing from transform DataFrame: {missing}"
            raise KeyError(msg)

        ohe_array = self._encoder.transform(df[self.columns].astype(str))
        ohe_df = pd.DataFrame(
            ohe_array,
            columns=self._feature_names,
            index=df.index,
        )

        # Drop original categorical columns and concatenate OHE output.
        result = pd.concat([df.drop(columns=self.columns), ohe_df], axis=1)

        logger.info(
            "CategoricalFeatureEncoder transform complete: "
            "%d rows x %d → %d columns.",
            len(df), len(df.columns), len(result.columns),
        )
        return result

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fit and transform in one call (for training data only).

        Args:
            df: Training DataFrame.

        Returns:
            Transformed DataFrame with OHE columns.
        """
        return self.fit(df).transform(df)

    @property
    def feature_names(self) -> list[str]:
        """Return the list of OHE output column names.

        Returns:
            List of OHE feature names, e.g.,
            ``["Compound_SOFT", "EventName_Bahrain..."]``.

        Raises:
            RuntimeError: If called before ``fit()``.
        """
        if not self._is_fitted:
            msg = "feature_names is only available after fit()."
            raise RuntimeError(msg)
        return self._feature_names

    @property
    def n_features_out(self) -> int:
        """Return the total number of OHE output features.

        Returns:
            Number of columns produced by ``transform()``.
        """
        return len(self._feature_names)
