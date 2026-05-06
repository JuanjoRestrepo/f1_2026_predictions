"""Track evolution feature engineering for F1 predictions.

Captures 'rubbering-in' effects by tracking the rolling median delta
to the fastest lap of the session or the degradation of lap times across
all drivers, indicating how the track grip is improving or worsening.
"""

import pandas as pd


def add_track_evolution_factor(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Calculate Track Evolution Factor based on rolling median of top lap times.

    As a session progresses, the track generally 'rubbers in', reducing
    overall lap times. This feature captures that macro-level trend by
    calculating the rolling median of the top 3 lap times in the last N laps.
    This helps the model distinguish tyre degradation from track improvement.

    Args:
        df: Silver or Gold laps DataFrame containing 'LapNumber' and 'LapTime_s'.
        window: Number of laps to roll over.

    Returns:
        DataFrame with 'Track_Evolution_Factor' column added.
    """
    if "LapTime_s" not in df.columns or "LapNumber" not in df.columns:
        df["Track_Evolution_Factor"] = 0.0
        return df

    # Group by LapNumber to get the median of the top 3 fastest times per lap
    # This represents the "ultimate pace" potential of the track at that lap
    lap_pace = (
        df.groupby("LapNumber")["LapTime_s"]
        .apply(lambda x: x.nsmallest(3).median())
        .reset_index(name="lap_potential_s")
    )

    # Calculate rolling delta (current lap potential vs window laps ago)
    # Negative means track is getting faster (rubbering in)
    lap_pace["Track_Evolution_Factor"] = lap_pace["lap_potential_s"].diff(
        periods=window
    )

    # Fill early laps with 0 (no evolution context yet)
    lap_pace["Track_Evolution_Factor"] = lap_pace["Track_Evolution_Factor"].fillna(0.0)

    # Merge back
    df = df.merge(
        lap_pace[["LapNumber", "Track_Evolution_Factor"]], on="LapNumber", how="left"
    )

    # Forward fill any missing values just in case
    df["Track_Evolution_Factor"] = df["Track_Evolution_Factor"].ffill().fillna(0.0)

    return df
