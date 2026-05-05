"""Reliability and wear feature engineering for F1 predictions.

Approximates PU (Power Unit) strain and brake wear proxies
using telemetry aggregates (e.g., Sector 3 variance for braking).
"""

import pandas as pd


def add_brake_wear_proxy(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """Calculate a Brake Wear Proxy using Sector 3 time variance.

    Sector 3 often contains heavy braking zones (e.g., Wall of Champions in Canada).
    Increased variance or degradation in Sector 3 times relative to overall pace
    can indicate brake fading or wear.

    Args:
        df: Laps DataFrame containing 'Sector3Time' (or 'Sector3Time_s') and 'Driver'.
        window: Rolling window for variance calculation.

    Returns:
        DataFrame with 'Brake_Wear_Proxy' column added.
    """
    # Try to resolve Sector 3 numeric time
    s3_col = "Sector3Time_s" if "Sector3Time_s" in df.columns else "Sector3Time"

    if s3_col not in df.columns or "Driver" not in df.columns:
        df["Brake_Wear_Proxy"] = 0.0
        return df

    # Ensure Sector 3 is numeric (it might be Timedelta in Silver layer)
    # If it is Timedelta, convert to seconds
    if pd.api.types.is_timedelta64_dtype(df[s3_col]):
        s3_seconds = df[s3_col].dt.total_seconds()
    else:
        s3_seconds = pd.to_numeric(df[s3_col], errors="coerce")

    # Calculate rolling variance of Sector 3 times per driver
    df["_s3_seconds"] = s3_seconds

    # Sort to ensure rolling applies chronologically
    if "LapNumber" in df.columns:
        df = df.sort_values(["Driver", "LapNumber"])

    df["Brake_Wear_Proxy"] = (
        df.groupby("Driver")["_s3_seconds"]
        .rolling(window=window, min_periods=1)
        .var()
        .reset_index(level=0, drop=True)
    )

    # Fill NAs and drop temp column
    df["Brake_Wear_Proxy"] = df["Brake_Wear_Proxy"].fillna(0.0)
    df = df.drop(columns=["_s3_seconds"])

    return df


def add_pu_strain_index(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Power Unit (PU) Strain Index.

    Approximates engine strain combining cumulative distance/laps and
    environmental factors (TrackTemp) which stress cooling.

    Args:
        df: Laps DataFrame.

    Returns:
        DataFrame with 'PU_Strain_Index' column added.
    """
    if "LapNumber" not in df.columns:
        df["PU_Strain_Index"] = 0.0
        return df

    # Base strain increases with laps
    base_strain = df["LapNumber"]

    # Multiplier for track temperature if available
    if "TrackTemp" in df.columns:
        # Normalize around 30C
        temp_multiplier = (df["TrackTemp"] / 30.0).clip(lower=0.5, upper=2.0)
    else:
        temp_multiplier = 1.0

    df["PU_Strain_Index"] = base_strain * temp_multiplier

    # Fill NAs
    df["PU_Strain_Index"] = df["PU_Strain_Index"].fillna(0.0)

    return df
