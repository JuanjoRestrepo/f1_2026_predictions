"""Multi-Era Normalization: Adjust historical lap times to 2026 regulations.

The 2026 FIA regulations introduce smaller, lighter cars with a 50/50
ICE/Electric power split and active aerodynamics. This significantly alters
the pace compared to the 2022-2025 ground-effect era.

This module applies a dynamic temporal penalty to historical data to
prevent the model from systemic bias (predicting cars are faster than
physically possible under the new rules).
"""

import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)


def apply_2026_regulations_penalty(df: pd.DataFrame) -> pd.DataFrame:
    """Apply a dynamic temporal penalty to LapTime_s for historical records.

    The penalty simulates the expected pace drop of the 2026 cars.
    It is composed of:
      - A flat base penalty (representing smaller tires, less downforce).
      - A dynamic penalty based on track downforce level.

    Args:
        df: DataFrame enriched with track metadata (must contain 'DownforceLevel_val').

    Returns:
        DataFrame with adjusted 'LapTime_s'.
    """
    if "LapTime_s" not in df.columns:
        return df

    adjusted = df.copy()

    # Only adjust data from before 2026
    mask = adjusted["Season"] < 2026

    if not mask.any():
        return adjusted

    # Baseline penalty: +1.5 seconds due to narrower tires and reduced floor aero.
    base_penalty = 1.5

    # Dynamic penalty: Tracks requiring High/Ultra-High downforce (val 4, 5)
    # will suffer more because the 2026 cars produce significantly less
    # absolute downforce. DownforceLevel_val ranges from 1 (Ultra-Low)
    # to 5 (Ultra-High).
    # Penalty: 0.2s per level of downforce required.
    downforce_multiplier = 0.2

    # Default to 3 (Medium) if track metadata is missing
    df_level = adjusted.loc[mask, "DownforceLevel_val"].fillna(3.0)

    total_penalty = base_penalty + (df_level * downforce_multiplier)

    adjusted.loc[mask, "LapTime_s"] = adjusted.loc[mask, "LapTime_s"] + total_penalty

    avg_penalty = total_penalty.mean()
    logger.info(
        "Applied 2026 Era Normalization to %d historical records. Avg penalty: +%.3fs",
        mask.sum(),
        avg_penalty,
    )

    return adjusted
