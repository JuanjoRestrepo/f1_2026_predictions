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
    """Join weather timeseries data with laps using temporal alignment.

    Uses ``pd.merge_asof`` to find the weather sample closest to the start
    of each lap. This provides high-fidelity environmental context.

    Args:
        df_laps: Clean laps DataFrame (must have 'Time' or 'LapStartTime').
        df_weather: Weather timeseries DataFrame from FastF1.

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

    if df_weather.empty:
        logger.warning("Weather DataFrame is empty. Filling weather features with NaN.")
        for col in ["AirTemp", "TrackTemp", "Humidity", "Rainfall", "WindSpeed"]:
            df_laps[col] = float("nan")
        return df_laps

    # Ensure both dataframes are sorted by time for merge_asof
    # Laps: we want weather at the START of the lap.
    # Note: FastF1 'Time' is completion time. 'LapStartTime' is start time.
    laps = df_laps.copy().sort_values("Time")
    weather = df_weather.copy().sort_values("Time")

    # Select only relevant weather columns
    weather = weather[
        ["Time", "AirTemp", "TrackTemp", "Humidity", "Rainfall", "WindSpeed"]
    ]

    # Perform temporal join
    # direction='backward' finds the last weather record BEFORE or AT the lap time
    result = pd.merge_asof(
        laps,
        weather,
        on="Time",
        direction="backward",
    )

    logger.info(
        "Weather features merged via temporal join (pd.merge_asof): %d rows",
        len(result),
    )
    return result
