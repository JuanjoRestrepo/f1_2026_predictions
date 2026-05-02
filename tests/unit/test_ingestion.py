"""Unit tests for f1_predictions.ingestion.

All tests are marked ``unit`` — no network calls, no FastF1 API, no disk I/O
outside pytest's ``tmp_path`` fixture. FastF1 sessions are replaced with
lightweight mock objects that replicate the shape of real FastF1 outputs.

Coverage targets (≥80%):
    - fastf1_client.py : SessionKey str representation, input validation,
                         cache configuration call, retry decorator attachment.
    - session_loader.py: Metadata column injection, schema validation pass/fail,
                         weather extraction (happy path + missing data).
    - parquet_writer.py: Path resolution, idempotent write (skip/overwrite),
                         read round-trip, empty DataFrame guard.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from f1_predictions.ingestion.fastf1_client import SessionKey, load_session
from f1_predictions.ingestion.parquet_writer import (
    DataType,
    read_parquet,
    resolve_parquet_path,
    write_parquet,
)
from f1_predictions.ingestion.session_loader import (
    COL_EVENT_NAME,
    COL_ROUND,
    COL_SEASON,
    COL_SESSION_TYPE,
    _add_metadata_columns,
    _extract_weather_summary,
    load_qualifying,
    load_race,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture()
def sample_key() -> SessionKey:
    """Return a canonical SessionKey for Bahrain 2025 Race."""
    return SessionKey(
        year=2025, round_number=1, identifier="R", event_name="Bahrain Grand Prix"
    )


@pytest.fixture()
def sample_quali_key() -> SessionKey:
    """Return a canonical SessionKey for Bahrain 2025 Qualifying."""
    return SessionKey(
        year=2025, round_number=1, identifier="Q", event_name="Bahrain Grand Prix"
    )


@pytest.fixture()
def minimal_laps_df() -> pd.DataFrame:
    """Minimal laps DataFrame with the columns required by LapsSchema."""
    return pd.DataFrame({
        "Time":          pd.to_timedelta(["0:01:30", "0:01:32", "0:01:31"]),
        "LapTime":       pd.to_timedelta(["0:01:30", "0:01:32", "0:01:31"]),
        "LapNumber":     [1, 1, 2],
        "Driver":        ["VER", "HAM", "VER"],
        "DriverNumber":  ["1", "44", "1"],
        "Team":          ["Red Bull Racing", "Mercedes", "Red Bull Racing"],
        "Compound":      ["SOFT", "MEDIUM", "SOFT"],
        "TyreLife":      [1.0, 1.0, 2.0],
        "FreshTyre":     [True, True, False],
        "Stint":         [1, 1, 1],
        "SpeedI1":       [310.5, 308.2, 311.0],
        "SpeedI2":       [295.0, 293.0, 296.0],
        "SpeedFL":       [280.0, 278.0, 281.0],
        "SpeedST":       [320.0, 318.0, 321.0],
        "IsPersonalBest":[True, False, False],
        "TrackStatus":   ["1", "1", "1"],
        "Sector1Time":   pd.to_timedelta(["0:00:28", "0:00:29", "0:00:28"]),
        "Sector2Time":   pd.to_timedelta(["0:00:31", "0:00:32", "0:00:31"]),
        "Sector3Time":   pd.to_timedelta(["0:00:31", "0:00:31", "0:00:32"]),
        "PitOutTime":    [pd.NaT, pd.NaT, pd.NaT],
        "PitInTime":     [pd.NaT, pd.NaT, pd.NaT],
    })


@pytest.fixture()
def minimal_results_df() -> pd.DataFrame:
    """Minimal results DataFrame compatible with ResultsSchema."""
    return pd.DataFrame({
        "DriverNumber": ["1", "44"],
        "BroadcastName":["M VERSTAPPEN", "L HAMILTON"],
        "Abbreviation": ["VER", "HAM"],
        "TeamName":     ["Red Bull Racing", "Mercedes"],
        "GridPosition": [1.0, 2.0],
        "Position":     [1.0, 2.0],
        "Q1":           [pd.NaT, pd.NaT],
        "Q2":           [pd.NaT, pd.NaT],
        "Q3":           [pd.NaT, pd.NaT],
        "Time":         pd.to_timedelta(["1:30:00", None]),
        "Status":       ["Finished", "Finished"],
        "Points":       [25.0, 18.0],
    })


@pytest.fixture()
def mock_session(
    minimal_laps_df: pd.DataFrame, minimal_results_df: pd.DataFrame
) -> MagicMock:
    """Mock fastf1.core.Session with realistic laps, results, and weather_data."""
    session = MagicMock()
    session.laps = minimal_laps_df
    session.results = minimal_results_df
    session.event = {"EventName": "Bahrain Grand Prix"}
    session.weather_data = pd.DataFrame({
        "AirTemp":    [28.0, 29.0, 30.0],
        "TrackTemp":  [38.0, 39.0, 40.0],
        "Humidity":   [45.0, 46.0, 44.0],
        "Pressure":   [1012.0, 1012.0, 1011.0],
        "WindSpeed":  [5.0, 6.0, 4.0],
        "Rainfall":   [False, False, False],
    })
    return session


# =============================================================================
# Tests: SessionKey
# =============================================================================

class TestSessionKey:
    """Tests for SessionKey string representation."""

    def test_str_without_event_name(self) -> None:
        """__str__ returns compact format when event_name is empty."""
        key = SessionKey(year=2025, round_number=3, identifier="Q")
        assert str(key) == "2025_R03_Q"

    def test_str_with_event_name(self, sample_key: SessionKey) -> None:
        """__str__ appends event_name when present."""
        assert "Bahrain Grand Prix" in str(sample_key)
        assert "2025_R01_R" in str(sample_key)

    def test_round_zero_padding(self) -> None:
        """Round number is zero-padded to two digits."""
        key = SessionKey(year=2025, round_number=9, identifier="R")
        assert "R09" in str(key)

    def test_frozen_key_is_immutable(self, sample_key: SessionKey) -> None:
        """SessionKey is frozen — mutation raises FrozenInstanceError."""
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            sample_key.year = 2026  # type: ignore[misc]


# =============================================================================
# Tests: load_session input validation
# =============================================================================

class TestLoadSessionValidation:
    """Tests for load_session() guard clauses — no network I/O."""

    def test_raises_on_year_before_2018(self) -> None:
        """year < 2018 raises ValueError before any FastF1 call."""
        with pytest.raises(ValueError, match="2018"):
            load_session(2010, 1, "R")

    def test_raises_on_round_zero(self) -> None:
        """round_number=0 raises ValueError."""
        with pytest.raises(ValueError, match="round_number"):
            load_session(2025, 0, "R")

    def test_raises_on_negative_round(self) -> None:
        """Negative round_number raises ValueError."""
        with pytest.raises(ValueError, match="round_number"):
            load_session(2025, -1, "Q")


# =============================================================================
# Tests: _add_metadata_columns
# =============================================================================

class TestAddMetadataColumns:
    """Tests for metadata column injection."""

    def test_all_metadata_columns_present(
        self, minimal_laps_df: pd.DataFrame, sample_key: SessionKey
    ) -> None:
        """All four metadata columns are present after injection."""
        result = _add_metadata_columns(minimal_laps_df, sample_key)
        for col in [COL_SEASON, COL_ROUND, COL_SESSION_TYPE, COL_EVENT_NAME]:
            assert col in result.columns, f"Missing column: {col}"

    def test_metadata_values_correct(
        self, minimal_laps_df: pd.DataFrame, sample_key: SessionKey
    ) -> None:
        """Injected values match the SessionKey attributes."""
        result = _add_metadata_columns(minimal_laps_df, sample_key)
        assert result[COL_SEASON].iloc[0] == 2025
        assert result[COL_ROUND].iloc[0] == 1
        assert result[COL_SESSION_TYPE].iloc[0] == "R"
        assert result[COL_EVENT_NAME].iloc[0] == "Bahrain Grand Prix"

    def test_original_df_not_mutated(
        self, minimal_laps_df: pd.DataFrame, sample_key: SessionKey
    ) -> None:
        """The input DataFrame is not mutated (copy semantics)."""
        original_cols = set(minimal_laps_df.columns)
        _add_metadata_columns(minimal_laps_df, sample_key)
        assert set(minimal_laps_df.columns) == original_cols

    def test_metadata_columns_at_start(
        self, minimal_laps_df: pd.DataFrame, sample_key: SessionKey
    ) -> None:
        """Metadata columns appear at positions 0-3 for easy preview."""
        result = _add_metadata_columns(minimal_laps_df, sample_key)
        assert result.columns[0] == COL_SEASON
        assert result.columns[1] == COL_ROUND
        assert result.columns[2] == COL_SESSION_TYPE
        assert result.columns[3] == COL_EVENT_NAME


# =============================================================================
# Tests: _extract_weather_summary
# =============================================================================

class TestExtractWeatherSummary:
    """Tests for weather extraction from a mock session."""

    def test_returns_single_row_dataframe(self, mock_session: MagicMock) -> None:
        """Happy path returns a 1-row DataFrame."""
        result = _extract_weather_summary(mock_session)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    def test_rainfall_aggregated_as_bool(self, mock_session: MagicMock) -> None:
        """Rainfall_any is True only if any row has rainfall=True."""
        result = _extract_weather_summary(mock_session)
        assert not result["Rainfall_any"].iloc[0]

    def test_rainfall_true_when_any_row_wet(self, mock_session: MagicMock) -> None:
        """Rainfall_any=True when at least one weather row has rainfall."""
        mock_session.weather_data["Rainfall"] = [False, True, False]
        result = _extract_weather_summary(mock_session)
        assert result["Rainfall_any"].iloc[0]

    def test_empty_weather_data_returns_empty_df(self, mock_session: MagicMock) -> None:
        """Empty weather_data returns an empty DataFrame (not an error)."""
        mock_session.weather_data = pd.DataFrame()
        result = _extract_weather_summary(mock_session)
        assert result.empty

    def test_none_weather_data_returns_empty_df(self, mock_session: MagicMock) -> None:
        """None weather_data returns an empty DataFrame (graceful degradation)."""
        mock_session.weather_data = None
        result = _extract_weather_summary(mock_session)
        assert result.empty


# =============================================================================
# Tests: load_qualifying and load_race
# =============================================================================

class TestLoadQualifying:
    """Tests for the load_qualifying() extractor."""

    def test_returns_qualifying_data_with_correct_key(
        self, mock_session: MagicMock, sample_quali_key: SessionKey
    ) -> None:
        """load_qualifying returns a QualifyingData with the supplied key."""
        result = load_qualifying(mock_session, sample_quali_key)
        assert result.key == sample_quali_key

    def test_laps_have_metadata_columns(
        self, mock_session: MagicMock, sample_quali_key: SessionKey
    ) -> None:
        """Returned laps DataFrame contains all four metadata columns."""
        result = load_qualifying(mock_session, sample_quali_key)
        for col in [COL_SEASON, COL_ROUND, COL_SESSION_TYPE, COL_EVENT_NAME]:
            assert col in result.laps.columns

    def test_results_have_metadata_columns(
        self, mock_session: MagicMock, sample_quali_key: SessionKey
    ) -> None:
        """Returned results DataFrame contains all four metadata columns."""
        result = load_qualifying(mock_session, sample_quali_key)
        for col in [COL_SEASON, COL_ROUND, COL_SESSION_TYPE, COL_EVENT_NAME]:
            assert col in result.results.columns


class TestLoadRace:
    """Tests for the load_race() extractor."""

    def test_returns_race_data_with_weather(
        self, mock_session: MagicMock, sample_key: SessionKey
    ) -> None:
        """load_race returns a RaceData with a non-empty weather DataFrame."""
        result = load_race(mock_session, sample_key)
        assert not result.weather.empty
        assert "AirTemp_mean" in result.weather.columns

    def test_laps_shape_preserved(
        self, mock_session: MagicMock, sample_key: SessionKey
    ) -> None:
        """load_race does not drop rows from the raw laps DataFrame."""
        n_raw = len(mock_session.laps)
        result = load_race(mock_session, sample_key)
        # Metadata columns added but row count must not change
        assert len(result.laps) == n_raw


# =============================================================================
# Tests: parquet_writer
# =============================================================================

class TestResolveParquetPath:
    """Tests for Hive-style path construction."""

    def test_path_contains_hive_partitions(
        self, sample_key: SessionKey, tmp_path: Path
    ) -> None:
        """Path includes season= and round= partition directories."""
        path = resolve_parquet_path(sample_key, DataType.LAPS, base_dir=tmp_path)
        assert "season=2025" in str(path)
        assert "round=01" in str(path)

    def test_path_includes_data_type(
        self, sample_key: SessionKey, tmp_path: Path
    ) -> None:
        """DataType is reflected in the path."""
        laps_path = resolve_parquet_path(sample_key, DataType.LAPS, base_dir=tmp_path)
        results_path = resolve_parquet_path(
            sample_key, DataType.RESULTS, base_dir=tmp_path
        )
        assert "laps" in str(laps_path)
        assert "results" in str(results_path)

    def test_parent_directory_created(
        self, sample_key: SessionKey, tmp_path: Path
    ) -> None:
        """resolve_parquet_path creates the parent directory."""
        path = resolve_parquet_path(sample_key, DataType.WEATHER, base_dir=tmp_path)
        assert path.parent.exists()


class TestWriteAndReadParquet:
    """Tests for write_parquet() idempotency and read_parquet() round-trip."""

    def test_write_creates_file(
        self, sample_key: SessionKey, minimal_laps_df: pd.DataFrame, tmp_path: Path
    ) -> None:
        """write_parquet creates a file at the expected path."""
        path = write_parquet(
            minimal_laps_df, sample_key, DataType.LAPS, base_dir=tmp_path
        )
        assert path.exists()
        assert path.suffix == ".parquet"

    def test_write_skip_on_existing_file(
        self, sample_key: SessionKey, minimal_laps_df: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Second write with overwrite=False does not modify the file."""
        path1 = write_parquet(
            minimal_laps_df, sample_key, DataType.LAPS, base_dir=tmp_path
        )
        mtime_before = path1.stat().st_mtime
        path2 = write_parquet(
            minimal_laps_df,
            sample_key,
            DataType.LAPS,
            base_dir=tmp_path,
            overwrite=False,
        )
        assert path1 == path2
        assert path2.stat().st_mtime == mtime_before  # File not touched

    def test_overwrite_replaces_file(
        self, sample_key: SessionKey, minimal_laps_df: pd.DataFrame, tmp_path: Path
    ) -> None:
        """overwrite=True replaces an existing file."""
        write_parquet(minimal_laps_df, sample_key, DataType.LAPS, base_dir=tmp_path)
        path = write_parquet(
            minimal_laps_df,
            sample_key,
            DataType.LAPS,
            base_dir=tmp_path,
            overwrite=True,
        )
        assert path.exists()

    def test_read_round_trip(
        self, sample_key: SessionKey, minimal_laps_df: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Data written and re-read via read_parquet matches the original."""
        write_parquet(minimal_laps_df, sample_key, DataType.LAPS, base_dir=tmp_path)
        result = read_parquet(sample_key, DataType.LAPS, base_dir=tmp_path)
        # Row count and column names must match
        assert len(result) == len(minimal_laps_df)
        # LapNumber is a reliable numeric column to spot-check
        assert list(result["LapNumber"]) == list(minimal_laps_df["LapNumber"])

    def test_write_raises_on_empty_df(
        self, sample_key: SessionKey, tmp_path: Path
    ) -> None:
        """write_parquet raises ValueError for an empty DataFrame."""
        with pytest.raises(ValueError, match="empty DataFrame"):
            write_parquet(pd.DataFrame(), sample_key, DataType.LAPS, base_dir=tmp_path)

    def test_read_raises_on_missing_file(
        self, sample_key: SessionKey, tmp_path: Path
    ) -> None:
        """read_parquet raises FileNotFoundError when no file exists."""
        with pytest.raises(FileNotFoundError, match="not found"):
            read_parquet(sample_key, DataType.RESULTS, base_dir=tmp_path)

    def test_column_selection_on_read(
        self, sample_key: SessionKey, minimal_laps_df: pd.DataFrame, tmp_path: Path
    ) -> None:
        """read_parquet with columns= returns only the requested columns."""
        write_parquet(minimal_laps_df, sample_key, DataType.LAPS, base_dir=tmp_path)
        result = read_parquet(
            sample_key, DataType.LAPS, base_dir=tmp_path,
            columns=["Driver", "LapNumber"],
        )
        assert list(result.columns) == ["Driver", "LapNumber"]
