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

import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)


def add_weather_features(
    df_laps: pd.DataFrame,
    df_weather: pd.DataFrame,
) -> pd.DataFrame:
    """Broadcast session weather summary features to all laps.

    Args:
        df_laps: Clean laps DataFrame.
        df_weather: Single-row weather summary DataFrame from session_loader.
            If empty, weather columns will be populated with NaN.

    Returns:
        New laps DataFrame with weather columns appended.

    Raises:
        TypeError: If inputs are not pandas DataFrames.
    """
    if not isinstance(df_laps, pd.DataFrame):
        msg = f"Expected df_laps to be pd.DataFrame, got {type(df_laps).__name__}"
        raise TypeError(msg)
    if not isinstance(df_weather, pd.DataFrame):
        msg = f"Expected df_weather to be pd.DataFrame, got {type(df_weather).__name__}"
        raise TypeError(msg)

    result = df_laps.copy()

    weather_cols = [
        "AirTemp_mean",
        "TrackTemp_mean",
        "Humidity_mean",
        "Rainfall_any",
    ]

    if df_weather.empty:
        logger.warning("Weather DataFrame is empty. Filling weather features with NaN.")
        for col in weather_cols:
            result[col] = float("nan")
        return result

    # Extract the first row as a dictionary
    weather_row = df_weather.iloc[0].to_dict()

    # Assign values to the laps dataframe
    for col in weather_cols:
        if col in weather_row:
            # Broadcast scalar value to the entire column
            result[col] = weather_row[col]
        else:
            result[col] = float("nan")

    logger.info(
        "Weather features broadcasted to laps: %s",
        ", ".join(weather_cols),
    )
    return result
