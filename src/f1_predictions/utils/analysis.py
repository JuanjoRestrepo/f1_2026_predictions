"""Utility functions for analyzing and ranking F1 prediction results."""

import numpy as np
import pandas as pd


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
