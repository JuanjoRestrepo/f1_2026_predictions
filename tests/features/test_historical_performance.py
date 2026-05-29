"""Unit tests for f1_predictions.features.historical_performance.

Tests cover all branches of add_historical_points:
  - None / empty history (Round 1 path → points = 0)
  - Normal path: cumulative driver and team points mapped correctly
  - Unknown driver/team (fillna=0 path)
  - Missing required columns in df_history_results → KeyError
  - Missing driver/team column in target df → graceful zero-fill
  - Laps df (Driver/Team) vs results df (Abbreviation/TeamName) detection
  - TypeError guard on non-DataFrame input
"""

import pandas as pd
import pytest

from f1_predictions.features.historical_performance import add_historical_points

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def laps_df() -> pd.DataFrame:
    """Minimal laps DataFrame with Driver and Team columns."""
    return pd.DataFrame(
        {
            "Driver": ["VER", "HAM", "LEC", "VER"],
            "Team": ["Red Bull Racing", "Mercedes", "Ferrari", "Red Bull Racing"],
            "LapTime_s": [90.0, 91.0, 92.0, 90.5],
        }
    )


@pytest.fixture()
def history_results() -> pd.DataFrame:
    """Season results from previous rounds."""
    return pd.DataFrame(
        {
            "Abbreviation": ["VER", "HAM", "LEC"],
            "TeamName": ["Red Bull Racing", "Mercedes", "Ferrari"],
            "Points": [50.0, 30.0, 25.0],
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _driver_pts(df: pd.DataFrame, driver: str) -> float:
    """Extract DriverPointsPreRace for a single driver abbreviation."""
    return float(df.loc[df["Driver"] == driver, "DriverPointsPreRace"].iloc[0])


def _team_pts(df: pd.DataFrame, team: str) -> float:
    """Extract TeamPointsPreRace for a single team name."""
    return float(df.loc[df["Team"] == team, "TeamPointsPreRace"].iloc[0])


# ---------------------------------------------------------------------------
# Round 1 / empty history path
# ---------------------------------------------------------------------------


class TestAddHistoricalPointsNoHistory:
    """Tests for the zero-fill path when no history is available."""

    def test_none_history_adds_zero_points(self, laps_df: pd.DataFrame) -> None:
        """None df_history_results must produce zero driver and team points."""
        result = add_historical_points(laps_df, df_history_results=None)
        assert "DriverPointsPreRace" in result.columns
        assert "TeamPointsPreRace" in result.columns
        assert (result["DriverPointsPreRace"] == 0.0).all()
        assert (result["TeamPointsPreRace"] == 0.0).all()

    def test_empty_history_adds_zero_points(self, laps_df: pd.DataFrame) -> None:
        """Empty df_history_results must produce zero driver and team points."""
        empty = pd.DataFrame(columns=["Abbreviation", "TeamName", "Points"])
        result = add_historical_points(laps_df, df_history_results=empty)
        assert (result["DriverPointsPreRace"] == 0.0).all()
        assert (result["TeamPointsPreRace"] == 0.0).all()

    def test_row_count_unchanged_no_history(self, laps_df: pd.DataFrame) -> None:
        """Row count must not change when history is None."""
        result = add_historical_points(laps_df, df_history_results=None)
        assert len(result) == len(laps_df)

    def test_original_columns_preserved_no_history(self, laps_df: pd.DataFrame) -> None:
        """Original columns must still be present in the output."""
        result = add_historical_points(laps_df, df_history_results=None)
        assert "Driver" in result.columns
        assert "LapTime_s" in result.columns


# ---------------------------------------------------------------------------
# Normal mapping path
# ---------------------------------------------------------------------------


class TestAddHistoricalPointsNormal:
    """Tests for the normal cumulative-points mapping path."""

    def test_driver_points_mapped_correctly(
        self, laps_df: pd.DataFrame, history_results: pd.DataFrame
    ) -> None:
        """DriverPointsPreRace must reflect cumulative points per driver."""
        result = add_historical_points(laps_df, history_results)
        assert _driver_pts(result, "VER") == 50.0
        assert _driver_pts(result, "HAM") == 30.0
        assert _driver_pts(result, "LEC") == 25.0

    def test_team_points_mapped_correctly(
        self, laps_df: pd.DataFrame, history_results: pd.DataFrame
    ) -> None:
        """TeamPointsPreRace must reflect cumulative points per team."""
        result = add_historical_points(laps_df, history_results)
        assert _team_pts(result, "Red Bull Racing") == 50.0
        assert _team_pts(result, "Mercedes") == 30.0
        assert _team_pts(result, "Ferrari") == 25.0

    def test_same_driver_multiple_rows_consistent(
        self, laps_df: pd.DataFrame, history_results: pd.DataFrame
    ) -> None:
        """All rows for the same driver must receive the same points value."""
        result = add_historical_points(laps_df, history_results)
        ver_rows = result[result["Driver"] == "VER"]["DriverPointsPreRace"]
        assert ver_rows.nunique() == 1

    def test_original_df_not_mutated(
        self, laps_df: pd.DataFrame, history_results: pd.DataFrame
    ) -> None:
        """The input laps DataFrame must not be modified in-place."""
        laps_before = laps_df.copy()
        add_historical_points(laps_df, history_results)
        pd.testing.assert_frame_equal(laps_df, laps_before)

    def test_unknown_driver_filled_with_zero(
        self, history_results: pd.DataFrame
    ) -> None:
        """Drivers not in history (e.g. rookies) must receive 0 points."""
        laps_with_rookie = pd.DataFrame(
            {
                "Driver": ["VER", "ROOKIE"],
                "Team": ["Red Bull Racing", "Williams"],
            }
        )
        result = add_historical_points(laps_with_rookie, history_results)
        rookie_pts = float(
            result.loc[result["Driver"] == "ROOKIE", "DriverPointsPreRace"].iloc[0]
        )
        assert rookie_pts == 0.0

    def test_output_dtype_is_float32(
        self, laps_df: pd.DataFrame, history_results: pd.DataFrame
    ) -> None:
        """Points columns must be float32 as specified in the implementation."""
        result = add_historical_points(laps_df, history_results)
        assert result["DriverPointsPreRace"].dtype == "float32"
        assert result["TeamPointsPreRace"].dtype == "float32"


# ---------------------------------------------------------------------------
# Abbreviation/TeamName column variant (results df, not laps df)
# ---------------------------------------------------------------------------


class TestAddHistoricalPointsAbbreviationVariant:
    """Tests for the Abbreviation/TeamName column variant (results-style df)."""

    def test_abbreviation_column_detected(self, history_results: pd.DataFrame) -> None:
        """When df has 'Abbreviation' instead of 'Driver', mapping must work."""
        results_df = pd.DataFrame(
            {
                "Abbreviation": ["VER", "HAM"],
                "TeamName": ["Red Bull Racing", "Mercedes"],
            }
        )
        result = add_historical_points(results_df, history_results)
        pts = float(
            result.loc[result["Abbreviation"] == "VER", "DriverPointsPreRace"].iloc[0]
        )
        assert pts == 50.0

    def test_team_name_column_detected(self, history_results: pd.DataFrame) -> None:
        """When df has 'TeamName' instead of 'Team', mapping must work."""
        results_df = pd.DataFrame(
            {
                "Abbreviation": ["VER"],
                "TeamName": ["Red Bull Racing"],
            }
        )
        result = add_historical_points(results_df, history_results)
        pts = float(
            result.loc[
                result["TeamName"] == "Red Bull Racing", "TeamPointsPreRace"
            ].iloc[0]
        )
        assert pts == 50.0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestAddHistoricalPointsErrors:
    """Tests for error-path behavior."""

    def test_missing_required_columns_raises_key_error(
        self, laps_df: pd.DataFrame
    ) -> None:
        """Missing required columns in df_history_results must raise KeyError."""
        bad_history = pd.DataFrame({"WrongCol": [1, 2, 3]})
        with pytest.raises(KeyError, match=r"Required column\(s\) missing"):
            add_historical_points(laps_df, bad_history)

    def test_non_dataframe_input_raises_type_error(self) -> None:
        """Non-DataFrame first argument must raise TypeError immediately."""
        with pytest.raises(TypeError, match=r"Expected df to be pd\.DataFrame"):
            add_historical_points({"Driver": ["VER"]})  # type: ignore[arg-type]

    def test_df_without_driver_col_fills_zero(
        self, history_results: pd.DataFrame
    ) -> None:
        """If neither 'Driver' nor 'Abbreviation' exist, must fill zeros."""
        no_driver_df = pd.DataFrame({"LapTime_s": [90.0, 91.0]})
        result = add_historical_points(no_driver_df, history_results)
        assert "DriverPointsPreRace" in result.columns
        assert (result["DriverPointsPreRace"] == 0.0).all()


# ---------------------------------------------------------------------------
# Cumulative summation across multiple rounds
# ---------------------------------------------------------------------------


class TestAddHistoricalPointsCumulative:
    """Tests for correct multi-round point accumulation."""

    def test_multi_round_points_summed(self, laps_df: pd.DataFrame) -> None:
        """Points from multiple rounds must be summed per driver."""
        multi_round_history = pd.DataFrame(
            {
                "Abbreviation": ["VER", "VER", "HAM"],
                "TeamName": [
                    "Red Bull Racing",
                    "Red Bull Racing",
                    "Mercedes",
                ],
                "Points": [25.0, 18.0, 15.0],
            }
        )
        result = add_historical_points(laps_df, multi_round_history)
        # VER: 25 + 18 = 43; HAM: 15
        assert _driver_pts(result, "VER") == 43.0
        assert _driver_pts(result, "HAM") == 15.0
