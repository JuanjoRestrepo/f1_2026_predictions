"""Unit tests for f1_predictions.utils.

Coverage targets (≥80%):
    - config.py        : Settings validation, path creation, lru_cache behavior.
    - logging_setup.py : Logger hierarchy, handler idempotency, level validation.
    - profiling.py     : quick_profile output, error conditions.

Markers:
    - All tests here are marked `unit` — no I/O, no network, no FastF1 calls.
      File system interactions are patched via tmp_path (pytest built-in).
"""

import logging
import sys
from pathlib import Path

import pandas as pd
import pytest

from f1_predictions.utils.logging_setup import (
    _ROOT_LOGGER_NAME,
    configure_root_pipeline_logger,
    get_logger,
)
from f1_predictions.utils.profiling import quick_profile

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def sample_laps_df() -> pd.DataFrame:
    """Minimal DataFrame mimicking a FastF1 laps subset.

    Returns:
        A 5-row DataFrame with numeric, string, and null columns.
    """
    return pd.DataFrame(
        {
            "LapTime": [90.1, 91.3, None, 89.8, 92.0],
            "Driver": ["VER", "HAM", "LEC", "VER", "HAM"],
            "Compound": ["SOFT", "MEDIUM", "SOFT", "SOFT", "HARD"],
            "LapNumber": [1, 1, 2, 2, 3],
            "SpeedI1": [310.5, 308.2, 312.0, 311.1, 309.4],
        }
    )


@pytest.fixture(autouse=True)
def reset_pipeline_logger() -> None:  # type: ignore[return]
    """Remove all handlers from the root pipeline logger between tests.

    Without this fixture, handlers accumulate across test functions because
    the logger persists in logging.Manager's logger dict for the process
    lifetime.
    """
    yield
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.handlers.clear()
    root.setLevel(logging.NOTSET)


# =============================================================================
# Tests: config.py
# =============================================================================


class TestSettings:
    """Tests for Settings validation and path resolution."""

    def test_default_log_level_is_info(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Settings defaults to INFO when F1_LOG_LEVEL is not set."""
        # Isolate from real .env by pointing env_file to a non-existent path
        monkeypatch.chdir(tmp_path)
        from f1_predictions.utils.config import Settings

        s = Settings()
        assert s.log_level == "INFO"

    def test_log_level_normalizes_to_uppercase(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """lowercase 'debug' env var is normalized to 'DEBUG'."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("F1_LOG_LEVEL", "debug")
        from f1_predictions.utils.config import Settings

        s = Settings()
        assert s.log_level == "DEBUG"

    def test_invalid_log_level_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unrecognized log level raises ValidationError on instantiation."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("F1_LOG_LEVEL", "VERBOSE")
        from pydantic import ValidationError

        from f1_predictions.utils.config import Settings

        with pytest.raises(ValidationError, match="log_level"):
            Settings()

    def test_paths_are_created_on_validation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_and_mkdir creates all configured directories on startup."""
        monkeypatch.chdir(tmp_path)
        from f1_predictions.utils.config import Settings

        s = Settings()
        # All path fields must exist after Settings() is instantiated
        for field_name in (
            "fastf1_cache_dir",
            "data_raw_dir",
            "data_processed_dir",
            "data_outputs_dir",
            "models_dir",
            "reports_dir",
        ):
            assert getattr(s, field_name).exists(), (
                f"{field_name} directory was not created by resolve_and_mkdir"
            )

    def test_target_season_bounds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """target_season below 2018 raises ValidationError."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("F1_TARGET_SEASON", "2010")
        from pydantic import ValidationError

        from f1_predictions.utils.config import Settings

        with pytest.raises(ValidationError):
            Settings()


# =============================================================================
# Tests: logging_setup.py
# =============================================================================


class TestGetLogger:
    """Tests for get_logger() hierarchy and naming."""

    def test_returns_logger_under_root_namespace(self) -> None:
        """get_logger(__name__) returns a child of 'f1_predictions'."""
        logger = get_logger("f1_predictions.ingestion.loader")
        assert (
            logger.name == "f1_predictions.f1_predictions.ingestion.loader"
            or logger.name.startswith("f1_predictions")
        )

    def test_non_namespaced_name_is_prefixed(self) -> None:
        """A bare module name is prefixed with 'f1_predictions.'."""
        logger = get_logger("some_module")
        assert logger.name.startswith(_ROOT_LOGGER_NAME)

    def test_already_namespaced_name_not_double_prefixed(self) -> None:
        """A name already starting with 'f1_predictions' is not double-prefixed."""
        logger = get_logger("f1_predictions.cleaning.laps")
        assert not logger.name.startswith("f1_predictions.f1_predictions")


class TestConfigureRootLogger:
    """Tests for configure_root_pipeline_logger() idempotency and level setting."""

    def test_sets_log_level_correctly(self) -> None:
        """configure_root_pipeline_logger sets the correct numeric level."""
        configure_root_pipeline_logger(level="DEBUG", enable_file_logging=False)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        assert root.level == logging.DEBUG

    def test_stream_handler_added_once(self) -> None:
        """Calling configure_root_pipeline_logger twice does not duplicate handlers."""
        configure_root_pipeline_logger(level="INFO", enable_file_logging=False)
        configure_root_pipeline_logger(level="INFO", enable_file_logging=False)
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        stream_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
        ]
        assert len(stream_handlers) == 1

    def test_file_handler_created(self, tmp_path: Path) -> None:
        """A RotatingFileHandler is created when enable_file_logging=True."""
        from logging.handlers import RotatingFileHandler

        configure_root_pipeline_logger(
            level="INFO",
            log_dir=tmp_path,
            filename="test_pipeline.log",
            enable_file_logging=True,
        )
        root = logging.getLogger(_ROOT_LOGGER_NAME)
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert (tmp_path / "test_pipeline.log").exists()

    def test_invalid_level_raises(self) -> None:
        """An invalid level string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid log level"):
            configure_root_pipeline_logger(level="TRACE", enable_file_logging=False)


# =============================================================================
# Tests: profiling.py
# =============================================================================


class TestQuickProfile:
    """Tests for quick_profile() output, error handling, and null warnings."""

    def test_runs_without_error_on_valid_df(
        self, sample_laps_df: pd.DataFrame, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """quick_profile completes without raising on a valid DataFrame."""
        quick_profile(sample_laps_df, name="Test Laps")
        captured = capsys.readouterr()
        assert "PROFILE" in captured.out
        assert "Test Laps" in captured.out

    def test_null_column_appears_in_output(
        self, sample_laps_df: pd.DataFrame, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Columns with nulls appear in the null summary section."""
        quick_profile(sample_laps_df, name="Null Test")
        captured = capsys.readouterr()
        assert "LapTime" in captured.out  # LapTime has 1 null in the fixture

    def test_no_nulls_prints_checkmark(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A null-free DataFrame prints the '✓ No null values detected.' message."""
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        quick_profile(df, name="Clean DF")
        captured = capsys.readouterr()
        assert "✓ No null values detected." in captured.out

    def test_raises_on_non_dataframe(self) -> None:
        """Passing a non-DataFrame raises TypeError."""
        with pytest.raises(TypeError, match="Expected pd.DataFrame"):
            quick_profile([1, 2, 3], name="Not a DF")  # type: ignore[arg-type]

    def test_raises_on_empty_dataframe(self) -> None:
        """An empty DataFrame raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            quick_profile(pd.DataFrame(), name="Empty")

    def test_duplicate_rows_detected(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A DataFrame with duplicate rows prints the duplicate warning."""
        df = pd.DataFrame({"a": [1, 1, 2], "b": [3, 3, 4]})
        quick_profile(df, name="Dupe DF")
        captured = capsys.readouterr()
        assert "duplicate row" in captured.out.lower()

    def test_no_duplicates_prints_checkmark(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A deduplicated DataFrame prints the '✓ No duplicate rows' message."""
        df = pd.DataFrame({"a": [1, 2, 3]})
        quick_profile(df, name="Unique DF")
        captured = capsys.readouterr()
        assert "✓ No duplicate rows detected." in captured.out

    def test_categorical_columns_shown(
        self, sample_laps_df: pd.DataFrame, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Categorical columns trigger the top-5 value count section."""
        quick_profile(sample_laps_df, name="Cat Test")
        captured = capsys.readouterr()
        assert "Driver" in captured.out
        assert "Compound" in captured.out
