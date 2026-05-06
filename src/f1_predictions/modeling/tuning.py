"""Optuna hyperparameter tuning for F1 pace regression models."""

from __future__ import annotations

from typing import Any

import optuna
import pandas as pd
import xgboost as xgb
from lightgbm import LGBMRegressor
from sklearn.metrics import (  # type: ignore[import-untyped]
    mean_absolute_error,
)

from f1_predictions.models.common import (
    align_feature_columns,
    chronological_split,
    prepare_feature_matrix,
)
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)


class OptunaTuner:
    """Bayesian hyperparameter tuner for tree-based F1 pace models."""

    def __init__(self, random_state: int = 42, n_trials: int = 50) -> None:
        """Initialize tuner.

        Args:
            random_state: Reproducibility seed.
            n_trials: Number of Optuna trials to run.
        """
        self.random_state = random_state
        self.n_trials = n_trials

    def tune_xgboost(
        self, df: pd.DataFrame, train_years: list[int], test_year: int
    ) -> dict[str, Any]:
        """Tune XGBoost hyperparameters."""
        logger.info(
            "Starting XGBoost hyperparameter tuning with %d trials...", self.n_trials
        )
        x_train, y_train, x_test, y_test = self._prepare_split(
            df, train_years, test_year
        )

        def objective(trial: optuna.Trial) -> float:
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 1000, step=100),
                "learning_rate": trial.suggest_float(
                    "learning_rate", 0.01, 0.2, log=True
                ),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "random_state": self.random_state,
                "n_jobs": -1,
            }
            model = xgb.XGBRegressor(**params)
            model.fit(
                x_train,
                y_train,
                eval_set=[(x_train, y_train), (x_test, y_test)],
                verbose=False,
            )
            y_pred = model.predict(x_test)
            return float(mean_absolute_error(y_test, y_pred))

        # Suppress optuna spam unless debugging
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=self.random_state),
        )
        study.optimize(objective, n_trials=self.n_trials)

        logger.info("XGBoost tuning complete. Best MAE: %.4f", study.best_value)
        logger.info("Best XGBoost params: %s", study.best_params)

        # Merge best params with base requirements
        best_params = study.best_params
        best_params["random_state"] = self.random_state
        best_params["n_jobs"] = -1
        return best_params

    def tune_lightgbm(
        self, df: pd.DataFrame, train_years: list[int], test_year: int
    ) -> dict[str, Any]:
        """Tune LightGBM hyperparameters."""
        logger.info(
            "Starting LightGBM hyperparameter tuning with %d trials...", self.n_trials
        )
        x_train, y_train, x_test, y_test = self._prepare_split(
            df, train_years, test_year
        )

        def objective(trial: optuna.Trial) -> float:
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 1000, step=100),
                "learning_rate": trial.suggest_float(
                    "learning_rate", 0.01, 0.2, log=True
                ),
                "max_depth": trial.suggest_int("max_depth", 3, 15),
                "num_leaves": trial.suggest_int("num_leaves", 20, 150),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "random_state": self.random_state,
                "n_jobs": -1,
                "verbose": -1,
            }
            model = LGBMRegressor(**params)  # type: ignore[arg-type]
            model.fit(
                x_train,
                y_train,
                eval_set=[(x_train, y_train), (x_test, y_test)],
                callbacks=[
                    # Suppress lightgbm spam
                ],
            )
            y_pred = model.predict(x_test)
            return float(mean_absolute_error(y_test, y_pred))

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=self.random_state),
        )
        study.optimize(objective, n_trials=self.n_trials)

        logger.info("LightGBM tuning complete. Best MAE: %.4f", study.best_value)
        logger.info("Best LightGBM params: %s", study.best_params)

        best_params = study.best_params
        best_params["random_state"] = self.random_state
        best_params["n_jobs"] = -1
        best_params["verbose"] = -1
        return best_params

    def _prepare_split(
        self, df: pd.DataFrame, train_years: list[int], test_year: int
    ) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
        """Prepare train/test arrays for tuning."""
        df_train, df_test = chronological_split(df, train_years, test_year)
        x_train, y_train = prepare_feature_matrix(df_train)
        x_test, y_test = prepare_feature_matrix(df_test)
        x_train, x_test, _ = align_feature_columns(x_train, x_test)
        return x_train, y_train, x_test, y_test
