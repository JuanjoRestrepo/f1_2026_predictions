"""Shared base class for tree-based F1 pace regressors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, cast

import numpy as np
import pandas as pd

from f1_predictions.models.common import (
    DEFAULT_TARGET_COLUMN,
    align_feature_columns,
    chronological_split,
    evaluate_regression,
    prepare_feature_matrix,
)
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)


class BasePaceRegressor(ABC):
    """Base implementation for tree-based lap-time regression models."""

    def __init__(self, random_state: int = 42) -> None:
        """Initialise the estimator and shared training state."""
        self.random_state = random_state
        self.model: object = self._build_estimator(random_state=random_state)
        self.features: list[str] = []

    @abstractmethod
    def _build_estimator(self, random_state: int) -> object:
        """Construct the underlying sklearn-compatible estimator."""

    @abstractmethod
    def _fit_model(
        self,
        x_train: pd.DataFrame,
        y_train: pd.Series,
        x_test: pd.DataFrame,
        y_test: pd.Series,
    ) -> None:
        """Fit the underlying estimator using the model-specific API."""

    def _prepare_data(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        """Prepare model features and target from a Gold-layer DataFrame."""
        return prepare_feature_matrix(df, target_column=DEFAULT_TARGET_COLUMN)

    def train_evaluate_chronological(
        self,
        df: pd.DataFrame,
        train_years: list[int],
        test_year: int,
    ) -> dict[str, float]:
        """Train and evaluate the model using a chronological season split."""
        logger.info(
            "Splitting data chronologically: Train=%s, Test=%s",
            train_years,
            test_year,
        )
        df_train, df_test = chronological_split(df, train_years, test_year)

        x_train, y_train = self._prepare_data(df_train)
        x_test, y_test = self._prepare_data(df_test)
        x_train, x_test, shared_cols = align_feature_columns(x_train, x_test)
        self.features = shared_cols

        logger.info("Training features (%d): %s", len(self.features), self.features)
        logger.info("Training %s on %d laps...", self.__class__.__name__, len(x_train))

        self._fit_model(x_train, y_train, x_test, y_test)

        logger.info("Evaluating on %d test laps...", len(x_test))
        model = cast(Any, self.model)
        y_pred = model.predict(x_test)
        metrics = evaluate_regression(y_test, y_pred)

        logger.info("=== Evaluation Results ===")
        logger.info("MAE:  %.3f seconds", metrics.mae)
        logger.info("RMSE: %.3f seconds", metrics.rmse)
        return metrics.as_dict()

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict lap times for new data using the fitted feature order."""
        if not self.features:
            msg = "Model must be trained before predict() is called."
            raise RuntimeError(msg)

        x, _ = prepare_feature_matrix(
            df,
            target_column=DEFAULT_TARGET_COLUMN,
            require_target=False,
        )
        missing = [feature for feature in self.features if feature not in x.columns]
        if missing:
            logger.warning("Missing features during inference: %s", missing)

        x = x.reindex(columns=self.features, fill_value=np.nan)
        model = cast(Any, self.model)
        return cast(np.ndarray, model.predict(x))
