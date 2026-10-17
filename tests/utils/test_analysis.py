"""Unit tests for src/f1_predictions/utils/analysis.py."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from f1_predictions.utils.analysis import (
    build_driver_standings,
    build_predictions_df,
    ensure_uncertainty_bounds,
)


class TestBuildPredictionsDf:
    """Tests for build_predictions_df."""

    def test_combines_metadata_and_predictions(self) -> None:
        metadata = pd.DataFrame(
            {
                "Driver": ["VER", "HAM"],
                "Team": ["Red Bull Racing", "Mercedes"],
                "LapNumber": [1, 1],
            }
        )
        y_pred_xgb = np.array([84.5, 84.8])
        quantile_preds_lgb = {
            0.05: np.array([84.1, 84.3]),
            0.50: np.array([84.5, 84.8]),
            0.95: np.array([85.0, 85.4]),
        }

        result = build_predictions_df(metadata, y_pred_xgb, quantile_preds_lgb)

        assert "predicted_laptime_xgb_s" in result.columns
        assert "predicted_laptime_lgb_p05_s" in result.columns
        assert "predicted_laptime_lgb_p50_s" in result.columns
        assert "predicted_laptime_lgb_p95_s" in result.columns
        assert len(result) == 2
        assert result.loc[0, "predicted_laptime_xgb_s"] == pytest.approx(84.5)
        assert result.loc[1, "predicted_laptime_lgb_p95_s"] == pytest.approx(85.4)


class TestBuildDriverStandings:
    """Tests for build_driver_standings."""

    def test_calculates_standings_and_ranks(self) -> None:
        df = pd.DataFrame(
            {
                "Driver": ["VER", "VER", "HAM", "HAM"],
                "Team": ["Red Bull", "Red Bull", "Mercedes", "Mercedes"],
                "predicted_laptime_lgb_p05_s": [80.0, 80.2, 81.0, 81.2],
                "predicted_laptime_lgb_p50_s": [81.0, 81.1, 82.0, 82.2],
                "predicted_laptime_lgb_p95_s": [82.0, 82.3, 83.0, 83.5],
            }
        )

        standings = build_driver_standings(df)

        assert list(standings.columns) == [
            "rank",
            "Driver",
            "Team",
            "lower_bound_s",
            "median_predicted_s",
            "upper_bound_s",
        ]
        assert len(standings) == 2
        # VER should be rank 1 (faster lap time)
        assert standings.loc[0, "Driver"] == "VER"
        assert standings.loc[0, "rank"] == 1
        assert standings.loc[1, "Driver"] == "HAM"
        assert standings.loc[1, "rank"] == 2

    def test_enforces_monotonicity(self) -> None:
        """Ensure lower <= median <= upper even when quantiles invert."""
        df = pd.DataFrame(
            {
                "Driver": ["VER"],
                "Team": ["Red Bull"],
                # Intentionally inverted: lower > median, upper < median
                "predicted_laptime_lgb_p05_s": [85.0],
                "predicted_laptime_lgb_p50_s": [82.0],
                "predicted_laptime_lgb_p95_s": [80.0],
            }
        )

        standings = build_driver_standings(df)
        row = standings.iloc[0]

        assert row["lower_bound_s"] <= row["median_predicted_s"]
        assert row["median_predicted_s"] <= row["upper_bound_s"]
        assert row["lower_bound_s"] == pytest.approx(82.0)
        assert row["upper_bound_s"] == pytest.approx(82.0)


class TestEnsureUncertaintyBounds:
    """Regression tests for synthesis of missing P05-P95 bound columns.

    Guards the fixed index-alignment bug: a bare ``pd.Series(0.0)`` aligns to
    label index 0 only, producing NaN bounds for every other row.
    """

    def test_synthesises_bounds_for_all_rows_when_std_present(self) -> None:
        df = pd.DataFrame(
            {
                "median_predicted_s": [80.0, 81.0, 82.0],
                "std_predicted_s": [0.2, 0.4, 0.6],
            }
        )

        result = ensure_uncertainty_bounds(df)

        assert not result["lower_bound_s"].isna().any()
        assert not result["upper_bound_s"].isna().any()
        assert result["lower_bound_s"].tolist() == pytest.approx(
            [80.0 - 1.645 * 0.2, 81.0 - 1.645 * 0.4, 82.0 - 1.645 * 0.6]
        )
        assert result["upper_bound_s"].tolist() == pytest.approx(
            [80.0 + 1.645 * 0.2, 81.0 + 1.645 * 0.4, 82.0 + 1.645 * 0.6]
        )

    def test_synthesises_zero_width_bounds_for_all_rows_when_std_absent(
        self,
    ) -> None:
        df = pd.DataFrame({"median_predicted_s": [80.0, 81.0, 82.0]})

        result = ensure_uncertainty_bounds(df)

        # Without a std column the band collapses onto the median — but every
        # row must still receive a finite (non-NaN) bound.
        assert not result["lower_bound_s"].isna().any()
        assert result["lower_bound_s"].tolist() == pytest.approx([80.0, 81.0, 82.0])
        assert result["upper_bound_s"].tolist() == pytest.approx([80.0, 81.0, 82.0])

    def test_noop_when_bounds_already_present(self) -> None:
        df = pd.DataFrame(
            {
                "median_predicted_s": [80.0],
                "lower_bound_s": [79.5],
                "upper_bound_s": [80.5],
            }
        )

        result = ensure_uncertainty_bounds(df)

        assert result["lower_bound_s"].tolist() == [79.5]
        assert result["upper_bound_s"].tolist() == [80.5]

    def test_raises_when_median_column_missing(self) -> None:
        df = pd.DataFrame({"driver": ["VER"]})

        with pytest.raises(KeyError, match="median_predicted_s"):
            ensure_uncertainty_bounds(df)
