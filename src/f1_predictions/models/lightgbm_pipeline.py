"""LightGBM regression pipeline for F1 pace prediction.

LightGBM is the natural benchmark partner for XGBoost on structured/tabular
data. It typically trains faster on sparse or high-dimensional inputs and gives
us a second tree-boosting baseline before we commit to a final model choice.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import lightgbm as lgb
import pandas as pd
from lightgbm import LGBMRegressor

from f1_predictions.models.base import BasePaceRegressor

LIGHTGBM_DEFAULT_PARAMS: dict[str, Any] = {
    "n_estimators": 500,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_samples": 20,
    "random_state": 42,
    "n_jobs": -1,
    "verbosity": -1,
}


class LightGBMPaceRegressor(BasePaceRegressor):
    """Wrapper for a LightGBM regressor predicting F1 lap times."""

    def __init__(
        self,
        random_state: int = 42,
        model_params: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialise the LightGBM regressor with tunable hyperparameters."""
        self._model_params = dict(LIGHTGBM_DEFAULT_PARAMS)
        self._model_params["random_state"] = random_state
        if model_params is not None:
            self._model_params.update(model_params)
        super().__init__(random_state=random_state)

    def _build_estimator(self, random_state: int) -> object:
        """Construct the LightGBM estimator."""
        return LGBMRegressor(**self._model_params)

    def _fit_model(
        self,
        x_train: pd.DataFrame,
        y_train: pd.Series,
        x_test: pd.DataFrame,
        y_test: pd.Series,
    ) -> None:
        """Fit LightGBM with an evaluation set for parity with XGBoost."""
        model = self.model
        assert isinstance(model, LGBMRegressor)
        model.fit(
            x_train,
            y_train,
            eval_set=[(x_train, y_train), (x_test, y_test)],
            eval_metric="mae",
            callbacks=[lgb.log_evaluation(period=0)],
        )
