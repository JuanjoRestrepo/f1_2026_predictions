"""External weather intelligence for proactive race-weekend forecasts.

The Friday forecast path needs information that FastF1 cannot provide before a
session has run. This module normalizes external forecast providers into a
small, stable contract focused on racing decisions: rain probability, air and
track temperature context, humidity, wind, and an operational risk label.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from f1_predictions.utils.config import Settings
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

VISUAL_CROSSING_PROVIDER = "visualcrossing"
OPENWEATHER_PROVIDER = "openweather"
UNAVAILABLE_PROVIDER = "unavailable"

RISK_DRY = "dry"
RISK_MIXED = "mixed"
RISK_WET = "wet"
RISK_UNKNOWN = "unknown"

_LOW_RAIN_THRESHOLD = 0.35
_HIGH_RAIN_THRESHOLD = 0.65


@dataclass(frozen=True, slots=True)
class CircuitLocation:
    """Circuit geolocation required by external weather providers."""

    event_name: str
    latitude: float
    longitude: float
    locality: str


@dataclass(frozen=True, slots=True)
class ForecastDay:
    """Provider-neutral daily forecast normalized for race engineering."""

    date: str
    rain_probability: float | None
    precipitation_mm: float | None
    air_temp_c: float | None
    humidity_pct: float | None
    wind_speed_mps: float | None
    conditions: str | None = None


@dataclass(frozen=True, slots=True)
class WeatherIntelligence:
    """Weather risk summary used by Friday forecasts and strategy narratives."""

    provider: str
    event_name: str
    generated_at_utc: str
    latitude: float | None
    longitude: float | None
    target_date: str | None
    race_day: ForecastDay | None
    forecast_days: list[ForecastDay]
    rain_probability: float | None
    risk_level: str
    confidence: str
    summary: str
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Serialize the forecast to a JSON-friendly dictionary."""
        return asdict(self)

    @property
    def is_wet_race(self) -> bool:
        """Return whether the forecast should drive wet-biased assumptions."""
        return self.risk_level == RISK_WET


class WeatherProvider(Protocol):
    """Protocol implemented by concrete external weather providers."""

    provider_name: str

    def fetch(
        self,
        location: CircuitLocation,
        start_date: date,
        end_date: date,
    ) -> list[ForecastDay]:
        """Return daily weather forecasts for a target date range."""


_CIRCUIT_LOCATIONS: dict[str, CircuitLocation] = {
    "Bahrain Grand Prix": CircuitLocation(
        "Bahrain Grand Prix", 26.0325, 50.5106, "Sakhir, Bahrain"
    ),
    "Saudi Arabian Grand Prix": CircuitLocation(
        "Saudi Arabian Grand Prix", 21.6319, 39.1044, "Jeddah, Saudi Arabia"
    ),
    "Australian Grand Prix": CircuitLocation(
        "Australian Grand Prix", -37.8497, 144.9680, "Melbourne, Australia"
    ),
    "Japanese Grand Prix": CircuitLocation(
        "Japanese Grand Prix", 34.8431, 136.5410, "Suzuka, Japan"
    ),
    "Chinese Grand Prix": CircuitLocation(
        "Chinese Grand Prix", 31.3389, 121.2200, "Shanghai, China"
    ),
    "Miami Grand Prix": CircuitLocation(
        "Miami Grand Prix", 25.9581, -80.2389, "Miami Gardens, USA"
    ),
    "Emilia Romagna Grand Prix": CircuitLocation(
        "Emilia Romagna Grand Prix", 44.3439, 11.7167, "Imola, Italy"
    ),
    "Monaco Grand Prix": CircuitLocation(
        "Monaco Grand Prix", 43.7347, 7.4206, "Monte Carlo, Monaco"
    ),
    "Spanish Grand Prix": CircuitLocation(
        "Spanish Grand Prix", 41.5700, 2.2611, "Montmelo, Spain"
    ),
    "Canadian Grand Prix": CircuitLocation(
        "Canadian Grand Prix", 45.5000, -73.5228, "Montreal, Canada"
    ),
    "Austrian Grand Prix": CircuitLocation(
        "Austrian Grand Prix", 47.2197, 14.7647, "Spielberg, Austria"
    ),
    "British Grand Prix": CircuitLocation(
        "British Grand Prix", 52.0786, -1.0169, "Silverstone, United Kingdom"
    ),
    "Hungarian Grand Prix": CircuitLocation(
        "Hungarian Grand Prix", 47.5789, 19.2486, "Mogyorod, Hungary"
    ),
    "Belgian Grand Prix": CircuitLocation(
        "Belgian Grand Prix", 50.4372, 5.9714, "Stavelot, Belgium"
    ),
    "Dutch Grand Prix": CircuitLocation(
        "Dutch Grand Prix", 52.3888, 4.5409, "Zandvoort, Netherlands"
    ),
    "Italian Grand Prix": CircuitLocation(
        "Italian Grand Prix", 45.6156, 9.2811, "Monza, Italy"
    ),
    "Azerbaijan Grand Prix": CircuitLocation(
        "Azerbaijan Grand Prix", 40.3725, 49.8533, "Baku, Azerbaijan"
    ),
    "Singapore Grand Prix": CircuitLocation(
        "Singapore Grand Prix", 1.2914, 103.8640, "Singapore"
    ),
    "United States Grand Prix": CircuitLocation(
        "United States Grand Prix", 30.1328, -97.6411, "Austin, USA"
    ),
    "Mexico City Grand Prix": CircuitLocation(
        "Mexico City Grand Prix", 19.4042, -99.0907, "Mexico City, Mexico"
    ),
    "Sao Paulo Grand Prix": CircuitLocation(
        "Sao Paulo Grand Prix", -23.7036, -46.6997, "Sao Paulo, Brazil"
    ),
    "Las Vegas Grand Prix": CircuitLocation(
        "Las Vegas Grand Prix", 36.1147, -115.1728, "Las Vegas, USA"
    ),
    "Qatar Grand Prix": CircuitLocation(
        "Qatar Grand Prix", 25.4900, 51.4542, "Lusail, Qatar"
    ),
    "Abu Dhabi Grand Prix": CircuitLocation(
        "Abu Dhabi Grand Prix", 24.4672, 54.6031, "Abu Dhabi, UAE"
    ),
}


def get_circuit_location(event_name: str) -> CircuitLocation | None:
    """Return geolocation metadata for an F1 event name."""
    return _CIRCUIT_LOCATIONS.get(event_name)


class VisualCrossingProvider:
    """Visual Crossing Timeline API adapter.

    The Timeline API accepts latitude,longitude path locations and supports
    daily forecast ranges. In metric units, ``windspeed`` is returned in km/h,
    so it is converted to m/s for consistency with OpenWeather.
    """

    provider_name = VISUAL_CROSSING_PROVIDER

    def __init__(self, api_key: str, timeout_seconds: float) -> None:
        """Initialize the provider with credentials and request timeout."""
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def fetch(
        self,
        location: CircuitLocation,
        start_date: date,
        end_date: date,
    ) -> list[ForecastDay]:
        """Fetch and normalize Visual Crossing daily forecasts."""
        loc = quote(f"{location.latitude},{location.longitude}", safe=",")
        url = (
            "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/"
            f"services/timeline/{loc}/{start_date.isoformat()}/{end_date.isoformat()}"
        )
        params = {
            "unitGroup": "metric",
            "include": "days",
            "elements": "datetime,temp,humidity,windspeed,precip,precipprob,conditions",
            "key": self._api_key,
        }
        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
        return parse_visual_crossing_days(response.json())


class OpenWeatherProvider:
    """OpenWeather One Call 3.0 adapter."""

    provider_name = OPENWEATHER_PROVIDER

    def __init__(self, api_key: str, timeout_seconds: float) -> None:
        """Initialize the provider with credentials and request timeout."""
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def fetch(
        self,
        location: CircuitLocation,
        start_date: date,
        end_date: date,
    ) -> list[ForecastDay]:
        """Fetch and normalize OpenWeather daily forecasts."""
        params: dict[str, str | int | float | bool | None] = {
            "lat": location.latitude,
            "lon": location.longitude,
            "units": "metric",
            "exclude": "current,minutely,hourly,alerts",
            "appid": self._api_key,
        }
        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.get(
                "https://api.openweathermap.org/data/3.0/onecall",
                params=params,
            )
            response.raise_for_status()
        days = parse_openweather_days(response.json())
        return [
            day
            for day in days
            if start_date <= date.fromisoformat(day.date) <= end_date
        ]


def parse_visual_crossing_days(payload: dict[str, Any]) -> list[ForecastDay]:
    """Normalize Visual Crossing daily payloads."""
    days = payload.get("days", [])
    if not isinstance(days, list):
        return []

    normalized: list[ForecastDay] = []
    for item in days:
        if not isinstance(item, dict) or not item.get("datetime"):
            continue
        precip_prob = _as_probability(item.get("precipprob"), percent_scale=True)
        wind_kph = _as_float(item.get("windspeed"))
        normalized.append(
            ForecastDay(
                date=str(item["datetime"]),
                rain_probability=precip_prob,
                precipitation_mm=_as_float(item.get("precip")),
                air_temp_c=_as_float(item.get("temp")),
                humidity_pct=_as_float(item.get("humidity")),
                wind_speed_mps=wind_kph / 3.6 if wind_kph is not None else None,
                conditions=_as_text(item.get("conditions")),
            )
        )
    return normalized


def parse_openweather_days(payload: dict[str, Any]) -> list[ForecastDay]:
    """Normalize OpenWeather One Call daily payloads."""
    days = payload.get("daily", [])
    if not isinstance(days, list):
        return []

    normalized: list[ForecastDay] = []
    for item in days:
        if not isinstance(item, dict) or item.get("dt") is None:
            continue
        weather = item.get("weather", [])
        conditions = None
        if isinstance(weather, list) and weather and isinstance(weather[0], dict):
            conditions = _as_text(weather[0].get("description"))
        temp = item.get("temp", {})
        day_temp = temp.get("day") if isinstance(temp, dict) else None
        normalized.append(
            ForecastDay(
                date=datetime.fromtimestamp(int(item["dt"]), tz=UTC).date().isoformat(),
                rain_probability=_as_probability(item.get("pop")),
                precipitation_mm=_as_float(item.get("rain")),
                air_temp_c=_as_float(day_temp),
                humidity_pct=_as_float(item.get("humidity")),
                wind_speed_mps=_as_float(item.get("wind_speed")),
                conditions=conditions,
            )
        )
    return normalized


def build_weather_intelligence(
    settings: Settings,
    event_name: str,
    target_date: str | None,
    now_utc: datetime | None = None,
) -> WeatherIntelligence:
    """Build external weather intelligence for a race weekend.

    Args:
        settings: Validated project settings.
        event_name: FastF1 event name.
        target_date: Race date as ``YYYY-MM-DD`` or ISO datetime string.
        now_utc: Optional clock override for deterministic tests.

    Returns:
        WeatherIntelligence. Missing provider keys return an explicit
        unavailable object rather than failing the pipeline.
    """
    now = now_utc or datetime.now(tz=UTC)
    location = get_circuit_location(event_name)
    if location is None:
        return _unavailable(
            event_name=event_name,
            target_date=target_date,
            now_utc=now,
            warning=f"No circuit coordinates configured for {event_name}.",
        )

    provider = _select_provider(settings)
    if provider is None:
        return _unavailable(
            event_name=event_name,
            target_date=target_date,
            now_utc=now,
            location=location,
            warning="No external weather API key configured.",
        )

    target = _parse_target_date(target_date)
    if target is None:
        target = now.date() + timedelta(days=settings.weather_forecast_days - 1)

    start_date = max(now.date(), target - timedelta(days=3))
    end_date = max(start_date, target)
    try:
        forecast_days = provider.fetch(location, start_date, end_date)
    except Exception as exc:
        logger.warning(
            "External weather provider %s failed: %s",
            provider.provider_name,
            exc,
        )
        return _unavailable(
            event_name=event_name,
            target_date=target.isoformat(),
            now_utc=now,
            location=location,
            warning=f"{provider.provider_name} request failed: {exc}",
        )

    race_day = choose_race_day(forecast_days, target)
    risk_level = classify_rain_risk(race_day.rain_probability if race_day else None)
    summary = summarize_weather_risk(event_name, race_day, risk_level)
    confidence = "external_forecast" if race_day else "missing_race_day"

    return WeatherIntelligence(
        provider=provider.provider_name,
        event_name=event_name,
        generated_at_utc=now.isoformat(),
        latitude=location.latitude,
        longitude=location.longitude,
        target_date=target.isoformat(),
        race_day=race_day,
        forecast_days=forecast_days,
        rain_probability=race_day.rain_probability if race_day else None,
        risk_level=risk_level,
        confidence=confidence,
        summary=summary,
        warnings=[] if race_day else ["Provider returned no forecast for race day."],
    )


def choose_race_day(
    forecast_days: list[ForecastDay], target_date: date
) -> ForecastDay | None:
    """Choose the forecast day nearest to race day."""
    if not forecast_days:
        return None
    return min(
        forecast_days,
        key=lambda day: abs((date.fromisoformat(day.date) - target_date).days),
    )


def classify_rain_risk(rain_probability: float | None) -> str:
    """Classify race-weekend rain risk for operational strategy decisions."""
    if rain_probability is None:
        return RISK_UNKNOWN
    if rain_probability >= _HIGH_RAIN_THRESHOLD:
        return RISK_WET
    if rain_probability >= _LOW_RAIN_THRESHOLD:
        return RISK_MIXED
    return RISK_DRY


def summarize_weather_risk(
    event_name: str, race_day: ForecastDay | None, risk_level: str
) -> str:
    """Create concise weather context for race reports and logs."""
    if race_day is None:
        return (
            f"No external race-day forecast is available for {event_name}; "
            "using conservative dry-weather assumptions."
        )
    rain_pct = (
        "unknown"
        if race_day.rain_probability is None
        else f"{race_day.rain_probability:.0%}"
    )
    temp = (
        "unknown" if race_day.air_temp_c is None else f"{race_day.air_temp_c:.1f}C air"
    )
    wind = (
        "unknown wind"
        if race_day.wind_speed_mps is None
        else f"{race_day.wind_speed_mps:.1f} m/s wind"
    )
    return (
        f"{event_name} race-day weather risk is {risk_level}: "
        f"{rain_pct} rain probability, {temp}, {wind}."
    )


def simulation_weather_features(
    intelligence: WeatherIntelligence | None,
    is_wet_race: bool = False,
) -> dict[str, float | bool]:
    """Convert external weather intelligence into model feature values."""
    race_day = intelligence.race_day if intelligence else None
    rain_probability = intelligence.rain_probability if intelligence else None
    rainfall = (
        bool(rain_probability is not None and rain_probability >= _HIGH_RAIN_THRESHOLD)
        or is_wet_race
    )
    air_temp = (
        race_day.air_temp_c if race_day and race_day.air_temp_c is not None else 22.0
    )
    humidity = (
        race_day.humidity_pct
        if race_day and race_day.humidity_pct is not None
        else 55.0
    )
    wind_speed = (
        race_day.wind_speed_mps
        if race_day and race_day.wind_speed_mps is not None
        else 4.0
    )
    track_temp = estimate_track_temperature(air_temp, rain_probability, rainfall)
    return {
        "AirTemp": air_temp,
        "TrackTemp": track_temp,
        "Humidity": humidity,
        "Rainfall": rainfall,
        "WindSpeed": wind_speed,
    }


def estimate_track_temperature(
    air_temp_c: float, rain_probability: float | None, is_wet: bool
) -> float:
    """Estimate track temperature when providers only expose air temperature."""
    if is_wet:
        return air_temp_c + 2.0
    if rain_probability is not None and rain_probability >= _LOW_RAIN_THRESHOLD:
        return air_temp_c + 6.0
    return air_temp_c + 12.0


def _select_provider(settings: Settings) -> WeatherProvider | None:
    provider_name = settings.weather_provider.lower()
    timeout = float(settings.weather_timeout_seconds)
    if provider_name == VISUAL_CROSSING_PROVIDER and settings.visual_crossing_api_key:
        return VisualCrossingProvider(settings.visual_crossing_api_key, timeout)
    if provider_name == OPENWEATHER_PROVIDER and settings.openweather_api_key:
        return OpenWeatherProvider(settings.openweather_api_key, timeout)
    if settings.visual_crossing_api_key:
        return VisualCrossingProvider(settings.visual_crossing_api_key, timeout)
    if settings.openweather_api_key:
        return OpenWeatherProvider(settings.openweather_api_key, timeout)
    return None


def _unavailable(
    event_name: str,
    target_date: str | None,
    now_utc: datetime,
    warning: str,
    location: CircuitLocation | None = None,
) -> WeatherIntelligence:
    return WeatherIntelligence(
        provider=UNAVAILABLE_PROVIDER,
        event_name=event_name,
        generated_at_utc=now_utc.isoformat(),
        latitude=location.latitude if location else None,
        longitude=location.longitude if location else None,
        target_date=target_date,
        race_day=None,
        forecast_days=[],
        rain_probability=None,
        risk_level=RISK_UNKNOWN,
        confidence=UNAVAILABLE_PROVIDER,
        summary=(
            f"No external weather forecast is available for {event_name}; "
            "Friday forecast keeps conservative dry-weather assumptions."
        ),
        warnings=[warning],
    )


def _parse_target_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, str | int | float):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_probability(value: object, percent_scale: bool = False) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    if percent_scale:
        number /= 100.0
    return min(max(number, 0.0), 1.0)


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
