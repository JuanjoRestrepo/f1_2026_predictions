"""Weather feature engineering for the f1_predictions pipeline.

Rationale:
    Track and air temperatures drastically affect tyre warm-up, degradation,
    and overall grip. Rainfall dictates compound selection and fundamentally
    alters the lap time baseline.

    This module takes the session-level weather summary from the Bronze/Silver
    layer and broadcasts it to every lap in the session. Since our target
    predicts lap-by-lap pace, the global session weather conditions act as
    baseline context for the XGBoost model.
"""

import numpy as np
import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

_WEATHER_COLS: list[str] = [
    "AirTemp",
    "TrackTemp",
    "Humidity",
    "Rainfall",
    "WindSpeed",
]


def add_weather_features(
    df_laps: pd.DataFrame,
    df_weather: pd.DataFrame,
) -> pd.DataFrame:
    """Join weather summary data with laps.

    The weather data provided by the pipeline is a session-level
    summary (e.g., Rainfall_any, AirTemp_mean). This function
    broadcasts those summary metrics to every lap in the session.

    Args:
        df_laps: Clean laps DataFrame.
        df_weather: Weather summary DataFrame with session aggregates.

    Returns:
        New laps DataFrame with weather features aligned to each lap.

    Raises:
        TypeError: If inputs are not pandas DataFrames.
    """
    if not isinstance(df_laps, pd.DataFrame):
        msg = f"Expected df_laps to be pd.DataFrame, got {type(df_laps).__name__}"
        raise TypeError(msg)
    if not isinstance(df_weather, pd.DataFrame):
        msg = f"Expected df_weather to be pd.DataFrame, got {type(df_weather).__name__}"
        raise TypeError(msg)

    laps = df_laps.copy()

    if df_weather.empty:
        logger.warning("Weather DataFrame is empty. Filling weather features with NaN.")
        return laps.assign(**dict.fromkeys(_WEATHER_COLS, np.nan))

    # Weather data is session-level; extract the single row
    weather_row = df_weather.iloc[0]

    # Map session-level aggregates to lap-level feature columns
    laps["AirTemp"] = weather_row.get("AirTemp_mean", np.nan)
    laps["TrackTemp"] = weather_row.get("TrackTemp_mean", np.nan)
    laps["Humidity"] = weather_row.get("Humidity_mean", np.nan)
    laps["Rainfall"] = weather_row.get("Rainfall_any", np.nan)
    laps["WindSpeed"] = weather_row.get("WindSpeed_mean", np.nan)

    # Older pipelines may produce raw fastf1 column names
    if pd.isna(laps["Rainfall"].iloc[0]) and "Rainfall" in weather_row:
        laps["Rainfall"] = weather_row["Rainfall"]

    # Ensure boolean type for Rainfall if it's not NaN
    if not laps["Rainfall"].isna().all():
        laps["Rainfall"] = laps["Rainfall"].astype(bool)

    laps = add_wet_race_pace_penalty(laps)

    logger.debug(
        "Added weather features to %d laps (Rainfall=%s).",
        len(laps),
        laps["Rainfall"].iloc[0] if not laps.empty else "N/A",
    )
    return laps


def add_wet_race_pace_penalty(laps: pd.DataFrame) -> pd.DataFrame:
    """Compute rain intensity index and wet-surface pace penalty seconds.

    Args:
        laps: Laps DataFrame containing Rainfall and TrackTemp.

    Returns:
        DataFrame enriched with rain_intensity_index and wet_pace_penalty_s.
    """
    result = laps.copy()

    rainfall = (
        result["Rainfall"].fillna(False).astype(bool)
        if "Rainfall" in result.columns
        else pd.Series(False, index=result.index)
    )
    track_temp = (
        result["TrackTemp"].fillna(30.0)
        if "TrackTemp" in result.columns
        else pd.Series(30.0, index=result.index)
    )

    # Wet surface penalty is higher when track temp is low & rainfall is active
    is_wet = rainfall.astype(float)
    temp_factor = np.clip((40.0 - track_temp) / 20.0, 0.5, 1.5)

    result["rain_intensity_index"] = (is_wet * temp_factor).astype("float32")
    # Base wet surface penalty delta: +12.5s for full wet condition
    result["wet_pace_penalty_s"] = (is_wet * 12.5 * temp_factor).astype("float32")

    return result
