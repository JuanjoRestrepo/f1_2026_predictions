"""Utility functions for analyzing and ranking F1 prediction results."""

import numpy as np
import pandas as pd


def build_predictions_df(
    metadata: pd.DataFrame,
    y_pred_xgb: np.ndarray,
    y_pred_lgb: np.ndarray,
) -> pd.DataFrame:
    """Combine metadata with model predictions into a single DataFrame."""
    df = metadata.copy()
    df["predicted_laptime_xgb_s"] = y_pred_xgb
    df["predicted_laptime_lgb_s"] = y_pred_lgb
    return df

def build_driver_standings(df: pd.DataFrame, pace_column: str) -> pd.DataFrame:
    """Calculate median predicted lap time per driver and rank them."""
    standings = (
        df.groupby(["Driver", "Team"])[pace_column]
        .median()
        .to_frame("median_predicted_s")
        .reset_index()
        .sort_values("median_predicted_s")
        .reset_index(drop=True)
    )
    standings.insert(0, "rank", standings.index + 1)
    return standings
