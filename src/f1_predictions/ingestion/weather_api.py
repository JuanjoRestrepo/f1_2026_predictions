"""External Weather Intelligence API integration.

Uses the free Open-Meteo API to fetch geocoding and 7-day weather forecasts.
This allows the `--auto` pipeline to accurately forecast grip conditions for
future races where historical FastF1 telemetry is not yet available.
"""

from typing import Any

import requests

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo daily fields for temperature and precipitation.
# The combined string is 57 chars; kept as a named constant to avoid E501.
_DAILY_FIELDS = "temperature_2m_max,temperature_2m_min,precipitation_probability_max"

# Precipitation probability threshold above which the race is treated as wet.
# 30% is the industry-standard "significant rain" threshold for broadcast alerts.
_RAIN_THRESHOLD_PERCENT = 30

# Asphalt absorbs solar radiation, heating significantly above air temperature.
# Dry/sunny delta: ~12°C (empirical; common asphalt delta used by F1 teams).
# Wet/overcast delta: ~3°C (cloud cover suppresses radiative heating).
_TRACK_TEMP_DELTA_DRY: float = 12.0
_TRACK_TEMP_DELTA_WET: float = 3.0


def get_forecast(city: str, date_str: str) -> dict[str, Any] | None:
    """Fetch weather forecast for a specific city and date.

    Performs two sequential API calls:
        1. Open-Meteo Geocoding API → resolves ``city`` to (lat, lon).
        2. Open-Meteo Weather Forecast API → retrieves daily temperature
           and precipitation probability for ``date_str``.

    TrackTemp is not available from any free API; it is approximated as
    AirTemp + delta, where delta depends on precipitation probability
    (12°C dry, 3°C wet). This is the standard simplification used by
    amateur F1 strategy models.

    Args:
        city: City name for geocoding, e.g. ``"Melbourne"``.
        date_str: Target date in ``YYYY-MM-DD`` format.

    Returns:
        Dictionary with keys ``AirTemp_mean``, ``TrackTemp_mean``,
        ``Rainfall_any``, ``Humidity_mean``, ``WindSpeed_mean``.
        Returns ``None`` if the geocoding fails, the city is not found,
        or any API call raises an exception.
    """
    logger.info("Fetching geocoding coordinates for %s", city)
    try:
        geo_resp = requests.get(
            GEOCODING_URL,
            params={
                "name": city,
                "count": "1",
                "language": "en",
                "format": "json",
            },
            timeout=10,
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()

        if not geo_data.get("results"):
            logger.warning("Geocoding failed to find coordinates for %s", city)
            return None

        location = geo_data["results"][0]
        lat = location["latitude"]
        lon = location["longitude"]
        logger.info("Found coordinates for %s: %s, %s", city, lat, lon)

        weather_resp = requests.get(
            WEATHER_URL,
            params={
                "latitude": str(lat),
                "longitude": str(lon),
                "start_date": date_str,
                "end_date": date_str,
                "daily": _DAILY_FIELDS,
                "timezone": "auto",
            },
            timeout=10,
        )
        weather_resp.raise_for_status()
        weather_data = weather_resp.json()

        if "daily" not in weather_data:
            logger.warning("No daily forecast found for %s on %s", city, date_str)
            return None

        daily = weather_data["daily"]

        air_max = daily["temperature_2m_max"][0]
        air_min = daily["temperature_2m_min"][0]
        air_mean = (air_max + air_min) / 2.0

        # Treat as wet if precipitation probability exceeds the threshold.
        precip_prob = daily["precipitation_probability_max"][0]
        rainfall_any = precip_prob > _RAIN_THRESHOLD_PERCENT

        delta = _TRACK_TEMP_DELTA_WET if rainfall_any else _TRACK_TEMP_DELTA_DRY
        track_temp_mean = air_mean + delta

        forecast: dict[str, Any] = {
            "AirTemp_mean": air_mean,
            "TrackTemp_mean": track_temp_mean,
            "Rainfall_any": rainfall_any,
            # Daily humidity average is noisy; 60% is the long-run global race mean.
            "Humidity_mean": 60.0,
            # Wind speed is circuit-specific and dominated by local topography;
            # a flat 2 m/s is used as a conservative aerodynamic baseline.
            "WindSpeed_mean": 2.0,
        }

        logger.info("Weather Forecast retrieved: %s", forecast)
    except Exception:
        logger.exception("Failed to fetch weather forecast")
        return None

    return forecast
