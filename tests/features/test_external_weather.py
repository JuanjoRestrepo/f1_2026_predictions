"""Tests for external weather intelligence normalization and risk logic."""

from __future__ import annotations

from datetime import UTC, datetime

from f1_predictions.features.external_weather import (
    RISK_DRY,
    RISK_MIXED,
    RISK_UNKNOWN,
    RISK_WET,
    ForecastDay,
    WeatherIntelligence,
    build_weather_intelligence,
    choose_race_day,
    classify_rain_risk,
    parse_openweather_days,
    parse_visual_crossing_days,
    simulation_weather_features,
)
from f1_predictions.utils.config import Settings


def test_parse_visual_crossing_days_normalizes_percent_probability() -> None:
    """Visual Crossing precipprob values are percent-scaled."""
    payload = {
        "days": [
            {
                "datetime": "2026-06-07",
                "temp": 21.5,
                "humidity": 72,
                "windspeed": 18,
                "precip": 4.2,
                "precipprob": 80,
                "conditions": "Rain",
            }
        ]
    }

    result = parse_visual_crossing_days(payload)

    assert len(result) == 1
    assert result[0].date == "2026-06-07"
    assert result[0].rain_probability == 0.8
    assert result[0].wind_speed_mps == 5.0


def test_parse_openweather_days_normalizes_daily_payload() -> None:
    """OpenWeather pop values are already 0-1 probabilities."""
    payload = {
        "daily": [
            {
                "dt": 1780790400,
                "pop": 0.45,
                "rain": 1.5,
                "temp": {"day": 24.0},
                "humidity": 66,
                "wind_speed": 6.2,
                "weather": [{"description": "light rain"}],
            }
        ]
    }

    result = parse_openweather_days(payload)

    assert len(result) == 1
    assert result[0].rain_probability == 0.45
    assert result[0].air_temp_c == 24.0
    assert result[0].conditions == "light rain"


def test_classify_rain_risk_thresholds() -> None:
    """Rain probability maps to dry, mixed, wet, or unknown risk labels."""
    assert classify_rain_risk(None) == RISK_UNKNOWN
    assert classify_rain_risk(0.2) == RISK_DRY
    assert classify_rain_risk(0.35) == RISK_MIXED
    assert classify_rain_risk(0.65) == RISK_WET


def test_choose_race_day_selects_nearest_forecast_date() -> None:
    """The race-day selector should pick the closest available forecast."""
    forecasts = [
        ForecastDay("2026-06-05", 0.2, None, None, None, None),
        ForecastDay("2026-06-08", 0.7, None, None, None, None),
    ]

    result = choose_race_day(forecasts, datetime(2026, 6, 7).date())

    assert result is not None
    assert result.date == "2026-06-08"
    assert result.rain_probability == 0.7


def test_build_weather_intelligence_without_key_is_explicit_fallback() -> None:
    """Missing API keys should not fail Friday forecast automation."""
    settings = Settings(
        visual_crossing_api_key=None,
        openweather_api_key=None,
    )

    result = build_weather_intelligence(
        settings=settings,
        event_name="Canadian Grand Prix",
        target_date="2026-06-07",
        now_utc=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert result.provider == "unavailable"
    assert result.risk_level == RISK_UNKNOWN
    assert result.latitude == 45.5
    assert result.warnings


def test_simulation_weather_features_uses_external_forecast() -> None:
    """External weather should fill model-compatible weather feature columns."""
    race_day = ForecastDay(
        date="2026-06-07",
        rain_probability=0.7,
        precipitation_mm=5.0,
        air_temp_c=20.0,
        humidity_pct=82.0,
        wind_speed_mps=7.0,
    )
    intelligence = WeatherIntelligence(
        provider="test",
        event_name="Canadian Grand Prix",
        generated_at_utc="2026-06-01T00:00:00+00:00",
        latitude=45.5,
        longitude=-73.5228,
        target_date="2026-06-07",
        race_day=race_day,
        forecast_days=[race_day],
        rain_probability=0.7,
        risk_level=RISK_WET,
        confidence="test",
        summary="wet test",
        warnings=[],
    )

    result = simulation_weather_features(intelligence)

    assert result["Rainfall"] is True
    assert result["AirTemp"] == 20.0
    assert result["TrackTemp"] == 22.0
    assert result["Humidity"] == 82.0
    assert result["WindSpeed"] == 7.0
