"""Unit tests for f1_predictions.cleaning.

All tests marked ``unit`` — pure DataFrame transformations, no I/O,
no FastF1 calls, no disk writes (except where tmp_path is used to test
the pipeline's Parquet read/write integration).

Coverage targets (≥80%):
    - normalizer.py      : Timedelta conversion, team mapping, driver normalization.
    - outlier_filter.py  : Each individual filter + apply_all_filters composition.
    - imputer.py         : Tyre ffill/mode, speed trap median, null drop.
    - pipeline.py        : Orchestration, idempotency, CleaningReport fields.
"""

import numpy as np
import pandas as pd
import pytest

from f1_predictions.cleaning.imputer import (
    drop_null_lap_times,
    impute_speed_traps,
    impute_tyre_data,
)
from f1_predictions.cleaning.normalizer import (
    CANONICAL_TEAM_MAP,
    convert_timedeltas_to_seconds,
    standardize_driver_identifiers,
    standardize_team_names,
)
from f1_predictions.cleaning.outlier_filter import (
    apply_all_filters,
    filter_impossible_lap_times,
    filter_in_laps,
    filter_neutralised_laps,
    filter_out_laps,
    filter_statistical_outliers,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def base_laps_df() -> pd.DataFrame:
    """Minimal raw laps DataFrame with Timedelta columns and tyre data."""
    n = 10
    return pd.DataFrame(
        {
            "Driver": ["VER"] * 5 + ["HAM"] * 5,
            "DriverNumber": ["1"] * 5 + ["44"] * 5,
            "Team": ["Oracle Red Bull Racing"] * 5 + ["Mercedes"] * 5,
            "LapNumber": list(range(1, 6)) * 2,
            "Stint": [1] * 5 + [1] * 5,
            "Compound": ["SOFT"] * 5 + ["MEDIUM"] * 5,
            "TyreLife": [1.0, 2.0, 3.0, 4.0, 5.0] * 2,
            "LapTime": pd.to_timedelta(
                [
                    "0:01:30",
                    "0:01:31",
                    "0:01:30",
                    "0:01:32",
                    "0:01:29",
                    "0:01:33",
                    "0:01:34",
                    "0:01:33",
                    "0:01:35",
                    "0:01:33",
                ]
            ),
            "Sector1Time": pd.to_timedelta(["0:00:28"] * n),
            "Sector2Time": pd.to_timedelta(["0:00:31"] * n),
            "Sector3Time": pd.to_timedelta(["0:00:31"] * n),
            "PitOutTime": pd.Series([pd.NaT] * n, dtype="timedelta64[ns]"),
            "PitInTime": pd.Series([pd.NaT] * n, dtype="timedelta64[ns]"),
            "SpeedI1": [310.0] * n,
            "SpeedI2": [295.0] * n,
            "SpeedFL": [280.0] * n,
            "SpeedST": [320.0] * n,
            "TrackStatus": ["1"] * n,
            "EventName": ["Bahrain Grand Prix"] * n,
        }
    )


@pytest.fixture()
def laps_with_seconds(base_laps_df: pd.DataFrame) -> pd.DataFrame:
    """Laps DataFrame after Timedelta conversion — LapTime_s present."""
    return convert_timedeltas_to_seconds(base_laps_df)


# =============================================================================
# Tests: normalizer.py
# =============================================================================


class TestConvertTimedeltasToSeconds:
    """Tests for Timedelta → decimal seconds conversion."""

    def test_laptime_s_column_created(self, base_laps_df: pd.DataFrame) -> None:
        """LapTime_s column is created from LapTime Timedelta."""
        result = convert_timedeltas_to_seconds(base_laps_df)
        assert "LapTime_s" in result.columns

    def test_laptime_s_is_float64(self, base_laps_df: pd.DataFrame) -> None:
        """Converted column has float64 dtype."""
        result = convert_timedeltas_to_seconds(base_laps_df)
        assert result["LapTime_s"].dtype == np.float64

    def test_laptime_value_correct(self, base_laps_df: pd.DataFrame) -> None:
        """90 second lap converts to exactly 90.0."""
        result = convert_timedeltas_to_seconds(base_laps_df)
        assert result["LapTime_s"].iloc[0] == pytest.approx(90.0)

    def test_original_timedelta_dropped_by_default(
        self, base_laps_df: pd.DataFrame
    ) -> None:
        """LapTime (Timedelta) is dropped when drop_original=True (default)."""
        result = convert_timedeltas_to_seconds(base_laps_df)
        assert "LapTime" not in result.columns

    def test_original_timedelta_kept_when_drop_false(
        self, base_laps_df: pd.DataFrame
    ) -> None:
        """LapTime Timedelta is preserved when drop_original=False."""
        result = convert_timedeltas_to_seconds(base_laps_df, drop_original=False)
        assert "LapTime" in result.columns
        assert "LapTime_s" in result.columns

    def test_missing_column_skipped_gracefully(
        self, base_laps_df: pd.DataFrame
    ) -> None:
        """Requesting a non-existent column does not raise — it is skipped."""
        result = convert_timedeltas_to_seconds(base_laps_df, columns=["NonExistentCol"])
        # No crash, no new column
        assert "NonExistentCol_s" not in result.columns

    def test_input_not_mutated(self, base_laps_df: pd.DataFrame) -> None:
        """Original DataFrame is not mutated (pure function)."""
        original_cols = set(base_laps_df.columns)
        convert_timedeltas_to_seconds(base_laps_df)
        assert set(base_laps_df.columns) == original_cols

    def test_raises_on_non_dataframe(self) -> None:
        """Passing a non-DataFrame raises TypeError."""
        with pytest.raises(TypeError):
            convert_timedeltas_to_seconds([1, 2, 3])  # type: ignore[arg-type]

    def test_nat_preserved_as_nan(self, base_laps_df: pd.DataFrame) -> None:
        """NaT Timedelta values become NaN floats (not 0.0)."""
        df = base_laps_df.copy()
        df.loc[0, "LapTime"] = pd.NaT
        result = convert_timedeltas_to_seconds(df)
        assert pd.isna(result["LapTime_s"].iloc[0])


class TestStandardizeTeamNames:
    """Tests for canonical team name mapping."""

    def test_known_variant_mapped(self, base_laps_df: pd.DataFrame) -> None:
        """'Oracle Red Bull Racing' maps to 'Red Bull'."""
        result = standardize_team_names(base_laps_df)
        assert "Red Bull" in result["Team"].values
        assert "Oracle Red Bull Racing" not in result["Team"].values

    def test_already_canonical_unchanged(self, base_laps_df: pd.DataFrame) -> None:
        """A value already in canonical form is not altered."""
        df = base_laps_df.copy()
        df["Team"] = "Red Bull"
        result = standardize_team_names(df)
        assert all(result["Team"] == "Red Bull")

    def test_unknown_team_preserved(self, base_laps_df: pd.DataFrame) -> None:
        """Unknown team names are preserved unchanged (not dropped or errored)."""
        df = base_laps_df.copy()
        df.loc[0, "Team"] = "Future Racing Team"
        result = standardize_team_names(df)
        assert result["Team"].iloc[0] == "Future Racing Team"

    def test_raises_on_missing_column(self, base_laps_df: pd.DataFrame) -> None:
        """Passing a non-existent team_column raises KeyError."""
        with pytest.raises(KeyError):
            standardize_team_names(base_laps_df, team_column="Constructor")

    def test_custom_map_applied(self, base_laps_df: pd.DataFrame) -> None:
        """A custom canonical_map overrides the default."""
        custom_map = {"Oracle Red Bull Racing": "RBR Custom"}
        result = standardize_team_names(base_laps_df, canonical_map=custom_map)
        assert "RBR Custom" in result["Team"].values

    def test_canonical_map_covers_known_constructors(self) -> None:
        """CANONICAL_TEAM_MAP contains entries for all current constructors."""
        canonical_teams = set(CANONICAL_TEAM_MAP.values())
        expected = {
            "Red Bull",
            "Mercedes",
            "Ferrari",
            "McLaren",
            "Aston Martin",
            "Alpine",
            "Williams",
            "RB",
            "Sauber",
            "Haas",
        }
        assert expected.issubset(canonical_teams)


class TestStandardizeDriverIdentifiers:
    """Tests for driver abbreviation normalization."""

    def test_lowercase_converted_to_uppercase(self, base_laps_df: pd.DataFrame) -> None:
        """Lowercase driver codes are uppercased."""
        df = base_laps_df.copy()
        df.loc[0, "Driver"] = "ver"
        result = standardize_driver_identifiers(df)
        assert result["Driver"].iloc[0] == "VER"

    def test_whitespace_stripped(self, base_laps_df: pd.DataFrame) -> None:
        """Leading/trailing whitespace is stripped from driver codes."""
        df = base_laps_df.copy()
        df.loc[0, "Driver"] = " VER "
        result = standardize_driver_identifiers(df)
        assert result["Driver"].iloc[0] == "VER"

    def test_raises_on_missing_column(self, base_laps_df: pd.DataFrame) -> None:
        """Missing driver_column raises KeyError."""
        with pytest.raises(KeyError):
            standardize_driver_identifiers(base_laps_df, driver_column="DriverCode")


# =============================================================================
# Tests: outlier_filter.py
# =============================================================================


class TestFilterOutLaps:
    """Tests for pit-exit lap removal."""

    def test_removes_rows_with_pit_out_time(
        self, laps_with_seconds: pd.DataFrame
    ) -> None:
        """Rows with non-null PitOutTime_s are removed."""
        df = laps_with_seconds.copy()
        df.loc[0, "PitOutTime_s"] = 5.0
        result = filter_out_laps(df)
        assert len(result) == len(df) - 1

    def test_no_removal_when_all_nan(self, laps_with_seconds: pd.DataFrame) -> None:
        """All-NaN PitOutTime_s column → no rows removed."""
        result = filter_out_laps(laps_with_seconds)
        assert len(result) == len(laps_with_seconds)

    def test_missing_column_returns_unchanged(
        self, laps_with_seconds: pd.DataFrame
    ) -> None:
        """Missing PitOutTime_s column → DataFrame returned unchanged."""
        df = laps_with_seconds.drop(columns=["PitOutTime_s"], errors="ignore")
        result = filter_out_laps(df)
        assert len(result) == len(df)


class TestFilterInLaps:
    """Tests for pit-entry lap removal."""

    def test_removes_rows_with_pit_in_time(
        self, laps_with_seconds: pd.DataFrame
    ) -> None:
        """Rows with non-null PitInTime_s are removed."""
        df = laps_with_seconds.copy()
        df.loc[2, "PitInTime_s"] = 85.0
        result = filter_in_laps(df)
        assert len(result) == len(df) - 1


class TestFilterNeutralisedLaps:
    """Tests for yellow flag / SC / VSC lap removal."""

    def test_removes_yellow_flag_laps(self, laps_with_seconds: pd.DataFrame) -> None:
        """TrackStatus='2' (yellow flag) rows are removed."""
        df = laps_with_seconds.copy()
        df.loc[3, "TrackStatus"] = "2"
        result = filter_neutralised_laps(df)
        assert len(result) == len(df) - 1

    def test_removes_safety_car_laps(self, laps_with_seconds: pd.DataFrame) -> None:
        """TrackStatus='4' (safety car) rows are removed."""
        df = laps_with_seconds.copy()
        df.loc[[1, 2], "TrackStatus"] = "4"
        result = filter_neutralised_laps(df)
        assert len(result) == len(df) - 2

    def test_green_flag_laps_retained(self, laps_with_seconds: pd.DataFrame) -> None:
        """TrackStatus='1' (clear) rows are all retained."""
        result = filter_neutralised_laps(laps_with_seconds)
        assert len(result) == len(laps_with_seconds)


class TestFilterImpossibleLapTimes:
    """Tests for out-of-range lap time removal."""

    def test_removes_nan_lap_times(self, laps_with_seconds: pd.DataFrame) -> None:
        """Rows with NaN LapTime_s are removed."""
        df = laps_with_seconds.copy()
        df.loc[0, "LapTime_s"] = float("nan")
        result = filter_impossible_lap_times(df)
        assert len(result) == len(df) - 1

    def test_removes_too_fast_laps(self, laps_with_seconds: pd.DataFrame) -> None:
        """Lap times below 50s (sensor error) are removed."""
        df = laps_with_seconds.copy()
        df.loc[0, "LapTime_s"] = 10.0
        result = filter_impossible_lap_times(df)
        assert len(result) == len(df) - 1

    def test_removes_too_slow_laps(self, laps_with_seconds: pd.DataFrame) -> None:
        """Lap times above 600s (formation lap / SC period) are removed."""
        df = laps_with_seconds.copy()
        df.loc[0, "LapTime_s"] = 700.0
        result = filter_impossible_lap_times(df)
        assert len(result) == len(df) - 1

    def test_valid_laps_all_retained(self, laps_with_seconds: pd.DataFrame) -> None:
        """All valid (~90s) laps are retained."""
        result = filter_impossible_lap_times(laps_with_seconds)
        assert len(result) == len(laps_with_seconds)


class TestFilterStatisticalOutliers:
    """Tests for MAD-based slow lap outlier removal."""

    def test_obvious_slow_lap_removed(self, laps_with_seconds: pd.DataFrame) -> None:
        """A lap 5x the typical time is flagged as a statistical outlier."""
        df = laps_with_seconds.copy()
        # Inject one extremely slow lap for VER in stint 1
        df.loc[4, "LapTime_s"] = 450.0  # ~5x normal
        result = filter_statistical_outliers(df, z_threshold=2.5)
        assert len(result) < len(df)

    def test_normal_laps_retained(self, laps_with_seconds: pd.DataFrame) -> None:
        """All normal laps (no outlier injection) are retained."""
        result = filter_statistical_outliers(laps_with_seconds, z_threshold=2.5)
        assert len(result) == len(laps_with_seconds)

    def test_fast_laps_never_removed(self, laps_with_seconds: pd.DataFrame) -> None:
        """Faster-than-median laps are never flagged as outliers."""
        df = laps_with_seconds.copy()
        df.loc[0, "LapTime_s"] = 75.0  # Faster than median ~90s
        result = filter_statistical_outliers(df, z_threshold=2.5)
        # The fast lap row must still be present
        assert 75.0 in result["LapTime_s"].values

    def test_skips_small_groups(self, laps_with_seconds: pd.DataFrame) -> None:
        """Groups with fewer than min_laps entries are skipped (not dropped)."""
        df = laps_with_seconds.copy()
        # Create a tiny group with 2 rows
        df_tiny = df.iloc[:2].copy()
        df_tiny["Driver"] = "NEW"
        df_combined = pd.concat([df, df_tiny], ignore_index=True)
        result = filter_statistical_outliers(df_combined, min_laps=4)
        # NEW driver's 2 rows should all be retained
        assert len(result[result["Driver"] == "NEW"]) == 2


class TestApplyAllFilters:
    """Tests for the composed filter pipeline."""

    def test_returns_tuple_of_df_and_stats(
        self, laps_with_seconds: pd.DataFrame
    ) -> None:
        """apply_all_filters returns a (DataFrame, dict) tuple."""
        result, stats = apply_all_filters(laps_with_seconds)
        assert isinstance(result, pd.DataFrame)
        assert isinstance(stats, dict)

    def test_stats_keys_present(self, laps_with_seconds: pd.DataFrame) -> None:
        """Stats dict contains all expected keys."""
        _, stats = apply_all_filters(laps_with_seconds)
        for key in (
            "impossible",
            "out_laps",
            "in_laps",
            "neutralised",
            "statistical_outliers",
            "total_removed",
            "retention_pct",
        ):
            assert key in stats, f"Missing stats key: {key}"

    def test_retention_pct_100_on_clean_data(
        self, laps_with_seconds: pd.DataFrame
    ) -> None:
        """100% retention when all laps are valid."""
        _, stats = apply_all_filters(laps_with_seconds)
        assert stats["retention_pct"] == pytest.approx(100.0)

    def test_total_removed_consistent(self, laps_with_seconds: pd.DataFrame) -> None:
        """total_removed == initial_len - result_len."""
        initial = len(laps_with_seconds)
        result, stats = apply_all_filters(laps_with_seconds)
        assert stats["total_removed"] == initial - len(result)


# =============================================================================
# Tests: imputer.py
# =============================================================================


class TestDropNullLapTimes:
    """Tests for null lap time row dropping."""

    def test_drops_nan_rows(self, laps_with_seconds: pd.DataFrame) -> None:
        """Rows with NaN LapTime_s are dropped and count returned."""
        df = laps_with_seconds.copy()
        df.loc[0, "LapTime_s"] = float("nan")
        result, n_dropped = drop_null_lap_times(df)
        assert n_dropped == 1
        assert len(result) == len(df) - 1

    def test_returns_zero_when_no_nulls(self, laps_with_seconds: pd.DataFrame) -> None:
        """Returns (df, 0) when no NaN lap times exist."""
        result, n_dropped = drop_null_lap_times(laps_with_seconds)
        assert n_dropped == 0
        assert len(result) == len(laps_with_seconds)


class TestImputeTyreData:
    """Tests for tyre data forward-fill and mode imputation."""

    def test_tyre_life_null_filled(self, laps_with_seconds: pd.DataFrame) -> None:
        """Null TyreLife mid-stint is forward-filled from previous lap."""
        df = laps_with_seconds.copy()
        df.loc[2, "TyreLife"] = float("nan")
        result, audit = impute_tyre_data(df)
        assert not result["TyreLife"].isna().any()
        assert audit["TyreLife"] >= 1

    def test_compound_null_mode_filled(self, laps_with_seconds: pd.DataFrame) -> None:
        """Null Compound is filled with the mode of the (Driver, Stint) group."""
        df = laps_with_seconds.copy()
        df.loc[1, "Compound"] = None
        result, audit = impute_tyre_data(df)
        assert result["Compound"].iloc[1] == "SOFT"
        assert audit["Compound"] == 1

    def test_no_nulls_audit_is_zero(self, laps_with_seconds: pd.DataFrame) -> None:
        """Audit values are 0 when no nulls exist."""
        _, audit = impute_tyre_data(laps_with_seconds)
        for v in audit.values():
            assert v == 0


class TestImputeSpeedTraps:
    """Tests for speed trap median imputation."""

    def test_null_speed_filled_with_driver_circuit_median(
        self, laps_with_seconds: pd.DataFrame
    ) -> None:
        """Null SpeedI1 is filled with the (Driver, EventName) group median."""
        df = laps_with_seconds.copy()
        df.loc[0, "SpeedI1"] = float("nan")
        result, audit = impute_speed_traps(df)
        assert not pd.isna(result["SpeedI1"].iloc[0])
        assert audit["SpeedI1"] == 1

    def test_all_non_null_no_imputation(self, laps_with_seconds: pd.DataFrame) -> None:
        """No imputation when all speed trap values are present."""
        _, audit = impute_speed_traps(laps_with_seconds)
        for v in audit.values():
            assert v == 0

    def test_all_null_group_falls_back_to_global_median(
        self, laps_with_seconds: pd.DataFrame
    ) -> None:
        """If entire group is null, global median is used as fallback."""
        df = laps_with_seconds.copy()
        # Set SpeedI1 null for all VER rows (entire group)
        df.loc[df["Driver"] == "VER", "SpeedI1"] = float("nan")
        result, audit = impute_speed_traps(df)
        # VER rows should now have the global median (from HAM rows = 310.0)
        ver_speeds = result.loc[result["Driver"] == "VER", "SpeedI1"]
        assert not ver_speeds.isna().any()
        assert audit["SpeedI1"] >= 5
