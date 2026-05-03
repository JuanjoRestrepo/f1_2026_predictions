"""Tests for XGBoost and LightGBM pace regressors."""

from __future__ import annotations

import pandas as pd
import pytest

from f1_predictions.models.lightgbm_pipeline import LightGBMPaceRegressor
from f1_predictions.models.xgboost_pipeline import F1PaceRegressor


@pytest.fixture()
def sample_model_df() -> pd.DataFrame:
    """Return a small multi-season dataset for model smoke tests."""

    rows: list[dict[str, object]] = []
    for season, base_time in ((2023, 90.0), (2024, 91.5)):
        for lap_number in range(1, 7):
            rows.append(
                {
                    "Season": season,
                    "RoundNumber": 1 if season == 2023 else 2,
                    "LapTime_s": base_time + lap_number * 0.2,
                    "LapNumber": lap_number,
                    "TyreLife": float(lap_number),
                    "Stint": 1,
                    "roll_laptime_3": base_time + lap_number * 0.15,
                    "roll_laptime_5": base_time + lap_number * 0.1,
                    "roll_std_3": 0.1 * lap_number,
                    "tyre_life_norm": lap_number / 6.0,
                    "degradation_slope": 0.2 * lap_number,
                    "Rainfall_any": lap_number % 2 == 0,
                    "TrackTemp_mean": 38.0 + lap_number,
                    "AirTemp_mean": 28.0 + lap_number,
                    "DriverPointsPreRace": 10.0 * lap_number,
                    "TeamPointsPreRace": 20.0 * lap_number,
                    "delta_to_fastest_s": 0.5 * lap_number,
                    "Driver": "VER",
                    "Team": "Red Bull",
                    "EventName": "Bahrain Grand Prix",
                    "Compound": "SOFT",
                }
            )

    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("regressor_cls", "model_params"),
    [
        (F1PaceRegressor, {"n_estimators": 10, "max_depth": 3}),
        (LightGBMPaceRegressor, {"n_estimators": 10, "num_leaves": 7}),
    ],
)
def test_tree_regressors_train_predict(
    sample_model_df: pd.DataFrame,
    regressor_cls: type[F1PaceRegressor] | type[LightGBMPaceRegressor],
    model_params: dict[str, int],
) -> None:
    """Both tree regressors should train, score, and predict on a smoke set."""

    regressor = regressor_cls(random_state=7, model_params=model_params)
    metrics = regressor.train_evaluate_chronological(
        sample_model_df,
        train_years=[2023],
        test_year=2024,
    )

    assert set(metrics) == {"MAE", "RMSE"}
    assert metrics["MAE"] >= 0.0
    assert metrics["RMSE"] >= 0.0
    assert regressor.features

    inference_df = sample_model_df.drop(columns=["LapTime_s"])
    preds = regressor.predict(inference_df)

    assert len(preds) == len(inference_df)
