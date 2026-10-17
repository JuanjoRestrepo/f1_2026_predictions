"""Unit tests for src/f1_predictions/evaluation/post_race_verdict.py."""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
import pytest

from f1_predictions.evaluation.post_race_verdict import (
    RaceVerdict,
    compute_verdict,
    load_actuals,
    load_predictions,
)


class TestLoadPredictions:
    """Tests for load_predictions."""

    def test_missing_file_raises_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Predictions file not found"):
            load_predictions(tmp_path / "nonexistent.csv")

    def test_missing_required_columns_raises_value_error(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "invalid_pred.csv"
        csv_file.write_text("Driver,OtherCol\nVER,1\n")
        with pytest.raises(ValueError, match="missing required columns"):
            load_predictions(csv_file)

    def test_loads_and_renames_xgb_columns(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "predictions.csv"
        df = pd.DataFrame(
            {
                "Driver": ["VER", "HAM", "LEC"],
                "predicted_laptime_xgb_s": [82.5, 83.0, 82.8],
            }
        )
        df.to_csv(csv_file, index=False)

        loaded = load_predictions(csv_file)
        assert "Predicted_LapTime_s" in loaded.columns
        assert "Predicted_Position" in loaded.columns
        assert loaded.loc[0, "Predicted_Position"] == 1
        assert loaded.loc[1, "Predicted_Position"] == 3
        assert loaded.loc[2, "Predicted_Position"] == 2


class TestLoadActuals:
    """Tests for load_actuals."""

    @patch("fastf1.get_session")
    def test_load_actuals_success(self, mock_get_session: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session.results = pd.DataFrame(
            {
                "Abbreviation": ["VER", "HAM"],
                "Position": [1, 2],
            }
        )
        mock_laps = pd.DataFrame(
            {
                "Driver": ["VER", "HAM"],
                "LapTime": [
                    pd.Timedelta(seconds=82.4),
                    pd.Timedelta(seconds=82.9),
                ],
            }
        )
        mock_session.laps = mock_laps
        mock_get_session.return_value = mock_session

        actuals = load_actuals(2026, 1)

        assert len(actuals) == 2
        assert "FastestLapTime" in actuals.columns
        assert actuals.loc[0, "Abbreviation"] == "VER"
        assert actuals.loc[0, "Position"] == 1

    @patch("fastf1.get_session")
    def test_load_actuals_failure_raises_runtime_error(
        self, mock_get_session: MagicMock
    ) -> None:
        mock_get_session.side_effect = Exception("FastF1 network timeout")
        with pytest.raises(RuntimeError, match="Failed to load FastF1 results"):
            load_actuals(2026, 99)

    @patch("fastf1.get_session")
    def test_load_actuals_tolerates_missing_lap_timing(
        self, mock_get_session: MagicMock
    ) -> None:
        """Finishing positions must survive an unavailable timing feed.

        Regression: accessing ``session.laps`` raises DataNotLoadedError when
        the timing data could not be fetched, which previously aborted the
        entire verdict even though positions were loaded.
        """
        mock_session = MagicMock()
        mock_session.results = pd.DataFrame(
            {"Abbreviation": ["VER", "HAM"], "Position": [1, 2]}
        )
        type(mock_session).laps = PropertyMock(
            side_effect=Exception("timing data not loaded")
        )
        mock_get_session.return_value = mock_session

        actuals = load_actuals(2024, 1)

        assert len(actuals) == 2
        assert actuals["FastestLapTime"].isna().all()
        assert actuals.loc[0, "Position"] == 1


class TestComputeVerdict:
    """Tests for compute_verdict."""

    def test_empty_overlap_returns_default_verdict(self) -> None:
        pred = pd.DataFrame(
            {
                "Driver": ["VER"],
                "Predicted_LapTime_s": [82.0],
                "Predicted_Position": [1],
            }
        )
        act = pd.DataFrame(
            {
                "Abbreviation": ["HAM"],
                "Position": [1],
                "FastestLapTime": [pd.Timedelta(seconds=82.0)],
            }
        )
        verdict = compute_verdict(pred, act, round_number=1, gp_name="Test GP")
        assert verdict.mae_lap_time_s == 999.0
        assert not verdict.winner_correct

    def test_valid_overlap_computes_metrics(self) -> None:
        drivers = ["VER", "HAM", "LEC", "NOR", "SAI", "RUS", "ALO", "STR", "PIA", "TSU"]
        pred = pd.DataFrame(
            {
                "Driver": drivers,
                "Predicted_LapTime_s": [82.0 + i * 0.2 for i in range(10)],
                "Predicted_Position": list(range(1, 11)),
            }
        )
        act = pd.DataFrame(
            {
                "Abbreviation": drivers,
                "Position": list(range(1, 11)),
                "FastestLapTime": [
                    pd.Timedelta(seconds=82.05 + i * 0.2) for i in range(10)
                ],
            }
        )
        verdict = compute_verdict(pred, act, round_number=1, gp_name="Bahrain GP")

        assert isinstance(verdict, RaceVerdict)
        assert verdict.round == 1
        assert verdict.gp_name == "Bahrain GP"
        assert verdict.winner_correct is True
        assert verdict.podium_accuracy_pct == pytest.approx(100.0)
        assert verdict.top10_accuracy_pct == pytest.approx(100.0)
        assert verdict.mae_lap_time_s == pytest.approx(0.05, abs=0.01)
        assert verdict.status == "excellent"
        assert len(verdict.key_misses) <= 3

    def test_missing_lap_timing_yields_partial_positional_verdict(self) -> None:
        """When the timing feed is unavailable, the verdict is positional-only.

        Regression: an all-NaT FastestLapTime column (datetime64 dtype) crashed
        ``pd.to_timedelta``, and a NaN MAE would have been misclassified as
        ``needs_improvement``. It must instead be an explicit ``partial`` status.
        """
        drivers = ["VER", "HAM", "LEC", "NOR", "SAI"]
        pred = pd.DataFrame(
            {
                "Driver": drivers,
                "Predicted_LapTime_s": [82.0 + i * 0.2 for i in range(5)],
                "Predicted_Position": list(range(1, 6)),
            }
        )
        act = pd.DataFrame(
            {
                "Abbreviation": drivers,
                "Position": list(range(1, 6)),
                "FastestLapTime": [pd.NaT] * 5,
            }
        )

        verdict = compute_verdict(pred, act, round_number=3, gp_name="Test GP")

        assert verdict.status == "partial"
        assert math.isnan(verdict.mae_lap_time_s)
        # Positional accuracy is still computed and correct.
        assert verdict.winner_correct is True
        assert verdict.podium_accuracy_pct == pytest.approx(100.0)
        assert verdict.key_misses == []


class TestRaceVerdictStatus:
    """Tests for explicit vs derived accuracy status."""

    def test_default_status_is_derived_from_mae(self) -> None:
        verdict = RaceVerdict(
            round=1,
            gp_name="Test GP",
            mae_lap_time_s=0.05,
            mape_pct=0.1,
            winner_correct=True,
            podium_accuracy_pct=100.0,
            top10_accuracy_pct=100.0,
        )
        assert verdict.status == "excellent"

    def test_explicit_status_is_preserved(self) -> None:
        """A non-accuracy status must not be overwritten by MAE classification.

        This is the safeguard that stops preview/unavailable notifications
        being mislabelled as a measured 'excellent' result.
        """
        verdict = RaceVerdict(
            round=1,
            gp_name="Test GP",
            mae_lap_time_s=0.0,
            mape_pct=0.0,
            winner_correct=False,
            podium_accuracy_pct=0.0,
            top10_accuracy_pct=0.0,
            status="preview",
        )
        assert verdict.status == "preview"

    def test_to_dict_round_trip_preserves_status(self) -> None:
        verdict = RaceVerdict(
            round=2,
            gp_name="Test GP",
            mae_lap_time_s=0.25,
            mape_pct=0.3,
            winner_correct=True,
            podium_accuracy_pct=66.7,
            top10_accuracy_pct=80.0,
        )
        restored = RaceVerdict(**verdict.to_dict())  # type: ignore[arg-type]
        assert restored.status == verdict.status == "good"
