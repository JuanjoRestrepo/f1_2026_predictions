"""Utility functions for analyzing and ranking F1 prediction results."""

import numpy as np
import pandas as pd

# Two-sided z-score for the 5th-95th percentile band of a normal distribution.
# Used to synthesise prediction-uncertainty bounds when an upstream producer
# emitted only a point estimate plus a standard deviation.
_P95_Z: float = 1.645


def build_predictions_df(
    metadata: pd.DataFrame,
    y_pred_xgb: np.ndarray,
    quantile_preds_lgb: dict[float, np.ndarray],
) -> pd.DataFrame:
    """Combine metadata with model predictions into a single DataFrame."""
    df = metadata.copy()
    df["predicted_laptime_xgb_s"] = y_pred_xgb

    for alpha, y_pred in quantile_preds_lgb.items():
        col_name = f"predicted_laptime_lgb_p{int(alpha * 100):02d}_s"
        df[col_name] = y_pred

    return df


def build_driver_standings(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate median predicted lap time per driver and rank them.

    Includes uncertainty intervals (P05 and P95) from LightGBM.
    """
    # Column mapping for clarity
    p05_col = "predicted_laptime_lgb_p05_s"
    p50_col = "predicted_laptime_lgb_p50_s"
    p95_col = "predicted_laptime_lgb_p95_s"

    standings = (
        df.groupby(["Driver", "Team"])
        .agg({p05_col: "median", p50_col: "median", p95_col: "median"})
        .rename(
            columns={
                p05_col: "lower_bound_s",
                p50_col: "median_predicted_s",
                p95_col: "upper_bound_s",
            }
        )
        .reset_index()
    )

    # Monotonicity check: ensure lower <= median <= upper
    # (Independent quantile models can occasionally cross in noisy regions)
    standings["lower_bound_s"] = np.minimum(
        standings["lower_bound_s"], standings["median_predicted_s"]
    )
    standings["upper_bound_s"] = np.maximum(
        standings["upper_bound_s"], standings["median_predicted_s"]
    )

    standings = standings.sort_values("median_predicted_s").reset_index(drop=True)
    standings.insert(0, "rank", standings.index + 1)
    return standings


def ensure_uncertainty_bounds(
    df: pd.DataFrame,
    std_col: str = "std_predicted_s",
    median_col: str = "median_predicted_s",
    z: float = _P95_Z,
) -> pd.DataFrame:
    """Guarantee ``lower_bound_s`` and ``upper_bound_s`` columns exist.

    Downstream consumers (residual analysis, uncertainty plots) require the
    P05-P95 band. When the upstream standings producer omitted it, the band is
    synthesised as ``median +/- z * std``.

    The standard-deviation series is built on ``df.index`` (or taken directly
    from the column, which already shares the index) so the arithmetic aligns
    by label. A bare ``pd.Series(0.0)`` would align to index ``[0]`` only and
    silently produce all-NaN bounds for every other row.

    Args:
        df: Standings DataFrame containing ``median_col``.
        std_col: Name of the standard-deviation column, if present.
        median_col: Name of the median-pace column.
        z: Two-sided z-score for the confidence band (default 1.645 = P05-P95).

    Returns:
        The same DataFrame with ``lower_bound_s``/``upper_bound_s`` populated.

    Raises:
        KeyError: If ``median_col`` is absent and no bounds can be derived.
    """
    if median_col not in df.columns:
        msg = f"'{median_col}' is required to synthesise uncertainty bounds."
        raise KeyError(msg)

    if "lower_bound_s" in df.columns and "upper_bound_s" in df.columns:
        return df

    if std_col in df.columns:
        half_width = z * df[std_col].astype(float).fillna(0.0)
    else:
        half_width = pd.Series(0.0, index=df.index)

    if "lower_bound_s" not in df.columns:
        df["lower_bound_s"] = df[median_col] - half_width
    if "upper_bound_s" not in df.columns:
        df["upper_bound_s"] = df[median_col] + half_width
    return df
