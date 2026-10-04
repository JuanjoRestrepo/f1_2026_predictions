"""Stacking regression pipeline for F1 pace prediction.

Combines XGBoost and LightGBM using a Bayesian Ridge meta-model.
This ensemble approach reduces prediction variance and biases,
targeting an MAE < 0.150s.
"""

from __future__ import annotations

import pandas as pd
import xgboost as xgb
from lightgbm import LGBMRegressor
from sklearn.ensemble import StackingRegressor  # type: ignore[import-untyped]
from sklearn.linear_model import BayesianRidge  # type: ignore[import-untyped]

from f1_predictions.models.base import BasePaceRegressor
from f1_predictions.models.lightgbm_pipeline import LIGHTGBM_DEFAULT_PARAMS
from f1_predictions.models.xgboost_pipeline import XGBOOST_DEFAULT_PARAMS


class StackingPaceRegressor(BasePaceRegressor):
    """Wrapper for a StackingRegressor combining XGBoost and LightGBM."""

    def __init__(self, random_state: int = 42) -> None:
        """Initialise the StackingRegressor."""
        self._xgb_params = dict(XGBOOST_DEFAULT_PARAMS)
        self._xgb_params["random_state"] = random_state

        self._lgb_params = dict(LIGHTGBM_DEFAULT_PARAMS)
        self._lgb_params["random_state"] = random_state

        super().__init__(random_state=random_state)

    def _build_estimator(self, random_state: int) -> object:
        """Construct the StackingRegressor with BayesianRidge meta-model."""
        from sklearn.ensemble import ExtraTreesRegressor

        base_estimators: list[tuple[str, object]] = [
            ("xgb", xgb.XGBRegressor(**self._xgb_params)),
            ("lgb", LGBMRegressor(**self._lgb_params)),
        ]

        try:
            import importlib

            catboost_mod = importlib.import_module("catboost")
            cat_cls = getattr(catboost_mod, "CatBoostRegressor")
            base_estimators.append(
                ("cat", cat_cls(verbose=0, random_state=random_state))
            )
        except Exception:
            base_estimators.append(
                (
                    "et",
                    ExtraTreesRegressor(
                        n_estimators=100,
                        max_depth=6,
                        random_state=random_state,
                    ),
                )
            )


        return StackingRegressor(
            estimators=base_estimators,
            final_estimator=BayesianRidge(),
            cv=5,
            n_jobs=-1,
            passthrough=False,
        )


    def _fit_model(
        self,
        x_train: pd.DataFrame,
        y_train: pd.Series,
        x_test: pd.DataFrame,
        y_test: pd.Series,
    ) -> None:
        """Fit the StackingRegressor.

        Note: eval_set is not natively supported by sklearn's StackingRegressor.
        We fit directly without eval_set; internal CV is handled by cv=5.
        """
        from typing import Any, cast

        cast(Any, self.model).fit(x_train, y_train)
