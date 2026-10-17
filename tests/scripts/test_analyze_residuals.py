"""Unit tests for scripts/analyze_residuals.py.

Focus: graceful degradation when the FastF1 timing feed is unavailable.

The residual analysis drives the retrain decision in ``main.py validate``.
When lap timing cannot be fetched, the function must return ``None`` (analysis
not possible) instead of raising — so the caller skips the retrain decision
rather than crashing on a transient feed outage.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
import pytest

from scripts.analyze_residuals import run_residual_analysis


def _write_standings(tmp_path: Path, event_dir: str) -> None:
    results_dir = tmp_path / "2026" / event_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "rank": [1, 2],
            "Driver": ["NOR", "VER"],
            "Team": ["McLaren", "Red Bull Racing"],
            "lower_bound_s": [88.0, 88.5],
            "median_predicted_s": [88.5, 89.0],
            "upper_bound_s": [89.0, 89.5],
        }
    ).to_csv(results_dir / "standings.csv", index=False)


def _fake_settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(reports_dir=str(tmp_path), fastf1_cache_dir=tmp_path)


@patch("scripts.analyze_residuals.fastf1")
@patch("scripts.analyze_residuals.get_settings")
def test_returns_none_when_lap_timing_unavailable(
    mock_settings: MagicMock, mock_fastf1: MagicMock, tmp_path: Path
) -> None:
    """Missing lap timing must yield None, not an exception."""
    mock_settings.return_value = _fake_settings(tmp_path)
    _write_standings(tmp_path, "Bahrain_Grand_Prix")

    mock_session = MagicMock()
    type(mock_session).laps = PropertyMock(
        side_effect=Exception("timing data not loaded")
    )
    mock_fastf1.get_session.return_value = mock_session

    result = run_residual_analysis(2026, 16, "Bahrain Grand Prix")

    assert result is None


@patch("scripts.analyze_residuals.fastf1")
@patch("scripts.analyze_residuals.get_settings")
def test_returns_mae_when_laps_available(
    mock_settings: MagicMock, mock_fastf1: MagicMock, tmp_path: Path
) -> None:
    """With lap timing present, a finite MAE is computed and returned."""
    mock_settings.return_value = _fake_settings(tmp_path)
    _write_standings(tmp_path, "Bahrain_Grand_Prix")

    laps = pd.DataFrame(
        {
            "Driver": ["NOR", "VER"],
            "PitInTime": [pd.NaT, pd.NaT],
            "PitOutTime": [pd.NaT, pd.NaT],
            "LapTime": [
                pd.Timedelta(seconds=88.6),
                pd.Timedelta(seconds=89.1),
            ],
        }
    )
    mock_session = MagicMock()
    mock_session.laps = laps
    mock_fastf1.get_session.return_value = mock_session

    result = run_residual_analysis(2026, 16, "Bahrain Grand Prix")

    assert result is not None
    # MAE = mean(|actual - predicted|) = mean(|0.1|, |0.1|) = 0.1
    assert result == pytest.approx(0.1)
