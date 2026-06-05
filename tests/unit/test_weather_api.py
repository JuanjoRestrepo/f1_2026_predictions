"""Unit tests for f1_predictions.ingestion.weather_api.

Tests are fully isolated from the network via pytest-mock patching of
requests.get. The module's external dependencies (Open-Meteo geocoding
and weather endpoints) are never called during the test suite.
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_geo_response(results: list | None = None) -> MagicMock:
    """Build a mock requests.Response for the geocoding endpoint."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"results": results or []}
    return resp


def _make_weather_response(
    temp_max: float = 28.0,
    temp_min: float = 18.0,
    precip_prob: int = 10,
) -> MagicMock:
    """Build a mock requests.Response for the weather forecast endpoint."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "daily": {
            "temperature_2m_max": [temp_max],
            "temperature_2m_min": [temp_min],
            "precipitation_probability_max": [precip_prob],
        }
    }
    return resp


GEO_RESULT = [{"latitude": 51.5074, "longitude": -0.1278}]  # London


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetForecastSuccess:
    """Tests for the sunny-day path of get_forecast()."""

    def test_returns_expected_keys(self) -> None:
        """get_forecast must return a dict with all five required feature keys."""
        geo_resp = _make_geo_response(GEO_RESULT)
        wx_resp = _make_weather_response(temp_max=28.0, temp_min=18.0, precip_prob=10)

        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = [geo_resp, wx_resp]
            from f1_predictions.ingestion.weather_api import get_forecast

            result = get_forecast("London", "2026-06-07")

        assert result is not None
        assert set(result.keys()) == {
            "AirTemp_mean",
            "TrackTemp_mean",
            "Rainfall_any",
            "Humidity_mean",
            "WindSpeed_mean",
        }

    def test_air_temp_is_mean_of_min_max(self) -> None:
        """AirTemp_mean = (max + min) / 2 (standard degree-day midpoint)."""
        geo_resp = _make_geo_response(GEO_RESULT)
        wx_resp = _make_weather_response(temp_max=30.0, temp_min=20.0, precip_prob=5)

        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = [geo_resp, wx_resp]
            from f1_predictions.ingestion.weather_api import get_forecast

            result = get_forecast("Monaco", "2026-05-25")

        assert result is not None
        assert result["AirTemp_mean"] == pytest.approx(25.0)

    def test_track_temp_dry_adds_12_degrees(self) -> None:
        """Track surface is ~12°C above air under sunny/dry conditions."""
        geo_resp = _make_geo_response(GEO_RESULT)
        # precip_prob=10 → dry (≤30% threshold) → +12°C delta
        wx_resp = _make_weather_response(temp_max=30.0, temp_min=20.0, precip_prob=10)

        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = [geo_resp, wx_resp]
            from f1_predictions.ingestion.weather_api import get_forecast

            result = get_forecast("Monza", "2026-09-07")

        assert result is not None
        assert result["TrackTemp_mean"] == pytest.approx(37.0)  # 25.0 + 12.0

    def test_track_temp_wet_adds_3_degrees(self) -> None:
        """Track surface delta shrinks to +3°C when rain is forecast (>30%)."""
        geo_resp = _make_geo_response(GEO_RESULT)
        # precip_prob=60 → wet (>30% threshold) → +3°C delta
        wx_resp = _make_weather_response(temp_max=20.0, temp_min=14.0, precip_prob=60)

        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = [geo_resp, wx_resp]
            from f1_predictions.ingestion.weather_api import get_forecast

            result = get_forecast("Spa", "2026-07-28")

        assert result is not None
        assert result["Rainfall_any"] is True
        assert result["TrackTemp_mean"] == pytest.approx(20.0)  # 17.0 + 3.0

    def test_dry_race_rainfall_is_false(self) -> None:
        """Rainfall_any is False when precipitation probability ≤30%."""
        geo_resp = _make_geo_response(GEO_RESULT)
        wx_resp = _make_weather_response(temp_max=32.0, temp_min=24.0, precip_prob=30)

        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = [geo_resp, wx_resp]
            from f1_predictions.ingestion.weather_api import get_forecast

            result = get_forecast("Bahrain", "2026-03-20")

        assert result is not None
        assert result["Rainfall_any"] is False

    def test_two_api_calls_are_made(self) -> None:
        """Exactly two GET calls must be made: one geocoding, one weather."""
        geo_resp = _make_geo_response(GEO_RESULT)
        wx_resp = _make_weather_response()

        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = [geo_resp, wx_resp]
            from f1_predictions.ingestion.weather_api import get_forecast

            get_forecast("Melbourne", "2026-03-14")

        assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# Geocoding failure tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetForecastGeocodingFailure:
    """Tests for geocoding edge cases and failures."""

    def test_returns_none_when_geo_results_empty(self) -> None:
        """get_forecast returns None if geocoding finds no matching city."""
        geo_resp = _make_geo_response(results=[])  # Empty results list

        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = [geo_resp]
            from f1_predictions.ingestion.weather_api import get_forecast

            result = get_forecast("NoSuchCity99", "2026-06-07")

        assert result is None

    def test_returns_none_when_geo_request_raises(self) -> None:
        """get_forecast returns None if the geocoding HTTP request fails."""
        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = Exception("Connection timeout")
            from f1_predictions.ingestion.weather_api import get_forecast

            result = get_forecast("Monaco", "2026-05-25")

        assert result is None


# ---------------------------------------------------------------------------
# Weather endpoint failure tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetForecastWeatherFailure:
    """Tests for weather API edge cases."""

    def test_returns_none_when_no_daily_key(self) -> None:
        """get_forecast returns None when the response lacks the 'daily' key."""
        geo_resp = _make_geo_response(GEO_RESULT)
        bad_wx = MagicMock()
        bad_wx.raise_for_status = MagicMock()
        bad_wx.json.return_value = {}  # Missing 'daily' key

        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = [geo_resp, bad_wx]
            from f1_predictions.ingestion.weather_api import get_forecast

            result = get_forecast("Monaco", "2026-05-25")

        assert result is None

    def test_returns_none_when_weather_request_raises(self) -> None:
        """get_forecast returns None if the weather HTTP request raises."""
        geo_resp = _make_geo_response(GEO_RESULT)

        with patch("f1_predictions.ingestion.weather_api.requests.get") as mock_get:
            mock_get.side_effect = [geo_resp, Exception("Weather API down")]
            from f1_predictions.ingestion.weather_api import get_forecast

            result = get_forecast("Monaco", "2026-05-25")

        assert result is None
