"""Tyre degradation feature engineering for the f1_predictions pipeline.

Rationale:
    Tyre degradation is one of the most predictive signals in F1 race modelling.
    A driver with a high degradation rate (steep positive slope of lap time vs
    tyre age) will lose significantly more time in long stints than one with
    a flat degradation curve, regardless of raw one-lap pace.

    The degradation slope is computed via ordinary least squares (OLS) linear
    regression of ``LapTime_s ~ TyreLife`` within each (Driver, Stint) group.
    The fitted slope (seconds per lap of tyre age) is then broadcast back to
    each lap row in that group as ``tyre_deg_slope``.

Why OLS here and not a rolling slope:
    A rolling slope over 3 laps would be too noisy at the start of a stint
    (only 1-2 data points) and would not produce a stable estimate of the
    true degradation rate. OLS over the full stint produces a single stable
    estimate that characterises the stint's fundamental behaviour. This is
    consistent with what F1 engineers use for strategy modelling.

Minimum stint length:
    OLS requires at least 2 data points. For stints with only 1 lap (e.g.,
    an early DNF or a very short stint under red flag conditions), the slope
    is set to NaN. The model handles NaN via XGBoost's native missing-value
    splitting. We do not fabricate a slope for a single-lap stint.

Edge case — perfect collinearity:
    If all laps in a stint have identical TyreLife values (sensor stuck),
    the OLS design matrix is rank-deficient. This is caught and logged as
    a warning; slope is set to NaN for that group.
"""

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Minimum laps in a stint to compute a meaningful OLS slope.
MIN_LAPS_FOR_SLOPE: int = 2

# Output column names.
COL_DEG_SLOPE: str = "tyre_deg_slope"
COL_DEG_INTERCEPT: str = "tyre_deg_intercept"
COL_TYRE_LIFE_NORM: str = "tyre_life_norm"

# Default grouping context for per-stint slope estimation.
DEFAULT_STINT_GROUPS: list[str] = ["Driver", "Stint"]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ols_slope(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
) -> tuple[float, float]:
    """Compute OLS slope and intercept for y ~ x.

    Uses numpy's closed-form OLS solution. Avoids scipy.stats.linregress
    to keep the dependency graph lean — this function is called thousands of
    times (once per stint) across a full season.

    Args:
        x: Independent variable array (TyreLife).
        y: Dependent variable array (LapTime_s).

    Returns:
        A tuple of (slope, intercept). Returns (nan, nan) if the computation
        is numerically undefined (e.g., zero variance in x).
    """
    n = len(x)
    if n < MIN_LAPS_FOR_SLOPE:
        return float("nan"), float("nan")

    x_mean = x.mean()
    y_mean = y.mean()
    ss_xx = float(((x - x_mean) ** 2).sum())

    if ss_xx == 0.0:
        # Perfect collinearity — TyreLife constant across the stint.
        return float("nan"), float("nan")

    slope = float(((x - x_mean) * (y - y_mean)).sum() / ss_xx)
    intercept = float(y_mean - slope * x_mean)
    return slope, intercept


# ── Public API ────────────────────────────────────────────────────────────────

def add_tyre_degradation_slope(
    df: pd.DataFrame,
    lap_time_col: str = "LapTime_s",
    tyre_life_col: str = "TyreLife",
    group_cols: list[str] | None = None,
    include_intercept: bool = False,
) -> pd.DataFrame:
    """Add per-stint OLS tyre degradation slope as a lap-level feature.

    For each (Driver, Stint) group, fits ``LapTime_s ~ TyreLife`` via OLS
    and broadcasts the slope back to every lap row in that group.

    ``tyre_deg_slope > 0``: lap time increases with tyre age (typical).
    ``tyre_deg_slope ≈ 0``: no observable degradation (HARD compound, low-deg circuit).
    ``tyre_deg_slope < 0``: lap time *improves* with tyre age (unusual; fuel-corrected
        pace improving faster than degradation, or a very short stint on fresh tyres).

    Args:
        df: Clean laps DataFrame from the Silver layer.
        lap_time_col: Lap time column in decimal seconds.
        tyre_life_col: Tyre life column (laps on current set).
        group_cols: Grouping context. Defaults to ``["Driver", "Stint"]``.
        include_intercept: If ``True``, also add ``tyre_deg_intercept``
            column (OLS intercept, representing predicted lap time at
            TyreLife=0). Defaults to ``False`` — not needed as a model feature
            but useful for debugging and stint reconstruction.

    Returns:
        New DataFrame with ``tyre_deg_slope`` (and optionally
        ``tyre_deg_intercept``) appended.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.
        KeyError: If required columns are absent.

    Example::

        from f1_predictions.features.tyre_degradation import add_tyre_degradation_slope

        df_feat = add_tyre_degradation_slope(clean_laps)
        # Typical output: VER SOFT stint1 slope ≈ 0.08 s/lap
        print(df_feat.groupby(["Driver", "Stint"])["tyre_deg_slope"].first())
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)

    groups = group_cols if group_cols is not None else DEFAULT_STINT_GROUPS
    required = [lap_time_col, tyre_life_col, *groups]
    missing = [c for c in required if c not in df.columns]
    if missing:
        msg = f"Required column(s) missing: {missing}. Available: {list(df.columns)}"
        raise KeyError(msg)

    result = df.copy()
    slopes: dict[object, float] = {}
    intercepts: dict[object, float] = {}
    n_skipped = 0

    for group_key, group_df in result.groupby(groups, dropna=True):
        valid = group_df[[lap_time_col, tyre_life_col]].dropna()
        if len(valid) < MIN_LAPS_FOR_SLOPE:
            slopes[group_key] = float("nan")
            intercepts[group_key] = float("nan")
            n_skipped += 1
            continue

        x: NDArray[np.float64] = valid[tyre_life_col].to_numpy(dtype=np.float64)
        y: NDArray[np.float64] = valid[lap_time_col].to_numpy(dtype=np.float64)
        slope, intercept = _ols_slope(x, y)

        if np.isnan(slope):
            logger.warning(
                "OLS slope undefined for group %s (TyreLife constant — sensor issue?). "
                "Setting slope=NaN.",
                group_key,
            )
            n_skipped += 1

        slopes[group_key] = slope
        intercepts[group_key] = intercept

    # Broadcast slope back to every row in each group.
    result[COL_DEG_SLOPE] = result.groupby(groups, group_keys=False).ngroup().map(
        {i: slopes.get(k, float("nan")) for i, k in enumerate(slopes)}
    )

    # Use direct groupby transform for clean broadcast.
    def _slope_for_group(group: pd.DataFrame) -> pd.Series:
        """Return the pre-computed slope broadcast to all rows in the group."""
        key = (
            tuple(group[groups].iloc[0])
            if len(groups) > 1
            else group[groups[0]].iloc[0]
        )
        s = slopes.get(key, float("nan"))
        return pd.Series([s] * len(group), index=group.index)

    result[COL_DEG_SLOPE] = (
        result.groupby(groups, group_keys=False)
        .apply(_slope_for_group)
    )

    if include_intercept:
        def _intercept_for_group(group: pd.DataFrame) -> pd.Series:
            """Return the pre-computed intercept broadcast to all rows."""
            key = (
                tuple(group[groups].iloc[0])
                if len(groups) > 1
                else group[groups[0]].iloc[0]
            )
            ic = intercepts.get(key, float("nan"))
            return pd.Series([ic] * len(group), index=group.index)

        result[COL_DEG_INTERCEPT] = (
            result.groupby(groups, group_keys=False)
            .apply(_intercept_for_group)
        )

    logger.info(
        "Tyre degradation slope computed: %d group(s), %d skipped "
        "(<min_laps or collinear). "
        "Column: %s",
        len(slopes), n_skipped, COL_DEG_SLOPE,
    )
    return result


def add_normalised_tyre_life(
    df: pd.DataFrame,
    tyre_life_col: str = "TyreLife",
    group_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Add TyreLife normalised to [0, 1] within each (Driver, Stint) group.

    Raw TyreLife ranges from 1 to ~40 laps depending on strategy. Normalising
    within the stint gives the model a relative tyre age feature (0 = fresh,
    1 = end of stint) that is comparable across different-length stints.

    Args:
        df: Clean laps DataFrame.
        tyre_life_col: Column with raw tyre life in laps.
        group_cols: Grouping context. Defaults to ``["Driver", "Stint"]``.

    Returns:
        New DataFrame with ``tyre_life_norm`` column appended.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.
        KeyError: If ``tyre_life_col`` is absent.
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)

    if tyre_life_col not in df.columns:
        msg = f"Column '{tyre_life_col}' not found. Available: {list(df.columns)}"
        raise KeyError(msg)

    groups = group_cols if group_cols is not None else DEFAULT_STINT_GROUPS
    result = df.copy()

    def _minmax_norm(series: pd.Series) -> pd.Series:
        """Min-max normalise; returns 0.0 if all values identical."""
        rng = series.max() - series.min()
        if rng == 0:
            return pd.Series(0.0, index=series.index)
        return pd.Series((series - series.min()) / rng, index=series.index)

    result[COL_TYRE_LIFE_NORM] = (
        result.groupby(groups, group_keys=False)[tyre_life_col]
        .transform(_minmax_norm)
    )
    logger.info("tyre_life_norm feature added (min-max per Driver/Stint).")
    return result
