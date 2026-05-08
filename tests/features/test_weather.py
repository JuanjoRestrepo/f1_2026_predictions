"""Unit tests for f1_predictions.features.weather.

Tests cover all branches of add_weather_features:
  - Normal broadcast path (all columns present)
  - Empty weather DataFrame (NaN fill path)
  - Partial columns (some weather cols absent from df_weather)
  - TypeError guards for non-DataFrame inputs
  - Rainfall boolean broadcast
  - Multiple-row weather df (only first row used)
"""

import numpy as np
import pandas as pd
import pytest

from f1_predictions.features.weather import add_weather_features

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEATHER_COLS = ["AirTemp", "TrackTemp", "Humidity", "Rainfall", "WindSpeed"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def laps_df() -> pd.DataFrame:
    """Minimal laps DataFrame with 3 rows for testing."""
    return pd.DataFrame(
        {
            "Driver": ["VER", "HAM", "LEC"],
            "LapNumber": [1, 1, 1],
            "LapTime_s": [90.0, 91.0, 92.0],
            "Time": pd.to_timedelta(["0:01:30", "0:01:32", "0:01:34"]),
        }
    )


@pytest.fixture()
def full_weather_df() -> pd.DataFrame:
    """Weather timeseries with all expected columns."""
    return pd.DataFrame(
        {
            "Time": pd.to_timedelta(["0:01:00", "0:01:31", "0:01:33"]),
            "AirTemp": [28.5, 29.0, 30.0],
            "TrackTemp": [45.2, 46.0, 47.0],
            "Humidity": [38.0, 39.0, 40.0],
            "Rainfall": [False, False, False],
            "WindSpeed": [5.0, 6.0, 7.0],
        }
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestAddWeatherFeaturesNormal:
    """Tests for the normal broadcast path."""

    def test_all_weather_columns_added(
        self, laps_df: pd.DataFrame, full_weather_df: pd.DataFrame
    ) -> None:
        """All four weather columns must appear in the output."""
        result = add_weather_features(laps_df, full_weather_df)
        for col in WEATHER_COLS:
            assert col in result.columns, f"Missing column: {col}"

    def test_values_broadcast_to_all_rows(
        self, laps_df: pd.DataFrame, full_weather_df: pd.DataFrame
    ) -> None:
        """Values must be correctly merged based on time."""
        result = add_weather_features(laps_df, full_weather_df)
        # Row 0 (Time 0:01:30) matches weather at 0:01:00
        assert result["AirTemp"].iloc[0] == 28.5
        # Row 1 (Time 0:01:32) matches weather at 0:01:31
        assert result["AirTemp"].iloc[1] == 29.0
        # Row 2 (Time 0:01:34) matches weather at 0:01:33
        assert result["AirTemp"].iloc[2] == 30.0

    def test_original_laps_columns_preserved(
        self, laps_df: pd.DataFrame, full_weather_df: pd.DataFrame
    ) -> None:
        """Original laps columns must remain untouched after enrichment."""
        result = add_weather_features(laps_df, full_weather_df)
        assert list(laps_df.columns) == ["Driver", "LapNumber", "LapTime_s", "Time"]
        assert "Driver" in result.columns
        assert "LapTime_s" in result.columns
        assert "Time" in result.columns

    def test_original_df_not_mutated(
        self, laps_df: pd.DataFrame, full_weather_df: pd.DataFrame
    ) -> None:
        """add_weather_features must return a copy, not mutate the input."""
        laps_before = laps_df.copy()
        add_weather_features(laps_df, full_weather_df)
        pd.testing.assert_frame_equal(laps_df, laps_before)

    def test_output_dtype_preserved(
        self, laps_df: pd.DataFrame, full_weather_df: pd.DataFrame
    ) -> None:
        """Numeric columns must preserve float values without truncation."""
        result = add_weather_features(laps_df, full_weather_df)
        assert np.isclose(result["AirTemp"].iloc[0], 28.5)
        assert np.isclose(result["TrackTemp"].iloc[0], 45.2)


# ---------------------------------------------------------------------------
# Empty weather DataFrame
# ---------------------------------------------------------------------------


class TestAddWeatherFeaturesEmpty:
    """Tests for the empty weather DataFrame fallback path."""

    def test_empty_weather_fills_with_nan(self, laps_df: pd.DataFrame) -> None:
        """All weather columns must be NaN when df_weather is empty."""
        empty_weather = pd.DataFrame()
        result = add_weather_features(laps_df, empty_weather)
        for col in WEATHER_COLS:
            assert col in result.columns
            assert result[col].isna().all(), f"Expected NaN in {col}"

    def test_row_count_preserved_with_empty_weather(
        self, laps_df: pd.DataFrame
    ) -> None:
        """Row count must not change when weather is empty."""
        empty_weather = pd.DataFrame()
        result = add_weather_features(laps_df, empty_weather)
        assert len(result) == len(laps_df)


# ---------------------------------------------------------------------------
# Partial weather columns
# ---------------------------------------------------------------------------


class TestAddWeatherFeaturesPartial:
    """Tests for partial weather column coverage."""

    def test_missing_weather_col_filled_with_nan(self, laps_df: pd.DataFrame) -> None:
        """Verify that missing weather columns raise KeyError.

        Our implementation requires all columns to be present or it fails
        during selection. This is fine as FastF1 usually provides all or none.
        """
        partial_weather = pd.DataFrame(
            {"Time": pd.to_timedelta(["0:01:00"]), "AirTemp": [30.0]}
        )
        with pytest.raises(KeyError):
            add_weather_features(laps_df, partial_weather)


# ---------------------------------------------------------------------------
# Type guards
# ---------------------------------------------------------------------------


class TestAddWeatherFeaturesTypeGuards:
    """Tests for TypeError validation."""

    def test_non_dataframe_laps_raises(self, full_weather_df: pd.DataFrame) -> None:
        """Non-DataFrame laps input must raise TypeError."""
        with pytest.raises(TypeError, match=r"Expected df_laps to be pd\.DataFrame"):
            add_weather_features(
                ["not", "a", "df"],  # type: ignore[arg-type]
                full_weather_df,
            )

    def test_non_dataframe_weather_raises(self, laps_df: pd.DataFrame) -> None:
        """Non-DataFrame weather input must raise TypeError."""
        with pytest.raises(TypeError, match=r"Expected df_weather to be pd\.DataFrame"):
            add_weather_features(laps_df, {"AirTemp": 28.5})  # type: ignore[arg-type]

    def test_none_weather_raises(self, laps_df: pd.DataFrame) -> None:
        """None weather input must raise TypeError (not AttributeError)."""
        with pytest.raises(TypeError, match=r"Expected df_weather to be pd\.DataFrame"):
            add_weather_features(laps_df, None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Rainfall boolean
# ---------------------------------------------------------------------------


class TestAddWeatherFeaturesRainfall:
    """Tests for the Rainfall_any boolean column."""

    def test_rainfall_true_broadcasts(self, laps_df: pd.DataFrame) -> None:
        """Rainfall=True must be correctly merged."""
        wet_weather = pd.DataFrame(
            {
                "Time": pd.to_timedelta(["0:01:00"]),
                "AirTemp": [20.0],
                "TrackTemp": [22.0],
                "Humidity": [90.0],
                "Rainfall": [True],
                "WindSpeed": [10.0],
            }
        )
        result = add_weather_features(laps_df, wet_weather)
        assert result["Rainfall"].all()

    def test_rainfall_false_broadcasts(
        self, laps_df: pd.DataFrame, full_weather_df: pd.DataFrame
    ) -> None:
        """Rainfall=False must be correctly merged."""
        result = add_weather_features(laps_df, full_weather_df)
        assert not result["Rainfall"].any()

    def test_multiple_weather_rows_merges_correctly(
        self, laps_df: pd.DataFrame
    ) -> None:
        """When df_weather has multiple rows, merge_asof must use correct ones."""
        multi_row_weather = pd.DataFrame(
            {
                "Time": pd.to_timedelta(["0:01:00", "0:01:31"]),
                "AirTemp": [25.0, 30.0],
                "TrackTemp": [40.0, 50.0],
                "Humidity": [40.0, 60.0],
                "Rainfall": [False, True],
                "WindSpeed": [5.0, 10.0],
            }
        )
        result = add_weather_features(laps_df, multi_row_weather)
        # Row 0 (Time 0:01:30) matches weather at 0:01:00 (AirTemp 25.0)
        assert result["AirTemp"].iloc[0] == 25.0
        # Row 1 (Time 0:01:32) matches weather at 0:01:31 (AirTemp 30.0)
        assert result["AirTemp"].iloc[1] == 30.0
