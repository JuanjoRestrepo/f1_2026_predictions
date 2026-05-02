"""XGBoost regression pipeline for F1 pace prediction.

Rationale:
    XGBoost is the state-of-the-art for tabular data, natively handling NaN
    values (crucial for missing telemetry/weather) and capturing non-linear
    interactions (e.g., TyreDegradation × TrackTemp).
    
    This module implements a chronological train/test split to prevent time
    leakage. Models are evaluated using Mean Absolute Error (MAE), which translates
    directly to seconds per lap — a highly interpretable business metric.
"""

from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, root_mean_squared_error  # type: ignore[import-untyped]

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# Features to exclude from training (identifiers and the target variable)
DROP_COLS = [
    "Driver",
    "EventName",
    "SessionType",
    "Time",
    "LapTime",
    "LapTime_s",
    "delta_to_fastest_s",
    "PitOutTime",
    "PitInTime",
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    "Compound",  # Handled via OHE features
]


class F1PaceRegressor:
    """Wrapper for XGBoost regressor predicting F1 lap times.

    This class encapsulates hyperparameter configuration, chronological
    splitting, training, and evaluation for the Gold layer feature matrix.
    """

    def __init__(self, random_state: int = 42) -> None:
        """Initialise the XGBoost regressor with default hyperparameters."""
        self.model = xgb.XGBRegressor(
            n_estimators=500,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=random_state,
            n_jobs=-1,  # Use all available CPU cores
        )
        self.features: list[str] = []

    def _prepare_data(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        """Extract features and target from the Gold DataFrame.

        Args:
            df: Gold layer DataFrame.

        Returns:
            Tuple of (X, y) where X is the feature matrix and y is the target (LapTime_s).
        """
        # Exclude laps where the target is missing
        clean_df = df.dropna(subset=["LapTime_s"]).copy()
        
        y = clean_df["LapTime_s"]
        
        # Drop identifiers and target columns
        cols_to_drop = [c for c in DROP_COLS if c in clean_df.columns]
        X = clean_df.drop(columns=cols_to_drop)

        # Ensure only numeric columns are passed to XGBoost
        # Categoricals should already be One-Hot Encoded
        X = X.select_dtypes(include=[np.number])

        return X, y

    def train_evaluate_chronological(
        self,
        df: pd.DataFrame,
        train_years: list[int],
        test_year: int,
    ) -> dict[str, float]:
        """Train and evaluate the model using a chronological split.

        Args:
            df: Full Gold layer DataFrame containing multiple seasons.
            train_years: List of seasons to use for training (e.g. [2023, 2024]).
            test_year: Season to use for validation (e.g. 2025).

        Returns:
            Dictionary containing MAE and RMSE metrics.
        """
        logger.info(
            "Splitting data chronologically: Train=%s, Test=%s",
            train_years,
            test_year,
        )

        train_mask = df["Season"].isin(train_years)
        test_mask = df["Season"] == test_year

        df_train = df[train_mask]
        df_test = df[test_mask]

        if df_train.empty:
            raise ValueError(f"No training data found for years {train_years}.")
        if df_test.empty:
            raise ValueError(f"No test data found for year {test_year}.")

        X_train, y_train = self._prepare_data(df_train)
        X_test, y_test = self._prepare_data(df_test)

        self.features = list(X_train.columns)
        logger.info("Training features (%d): %s", len(self.features), self.features)

        logger.info("Training XGBoost Regressor on %d laps...", len(X_train))
        
        # We pass early stopping in fit using an evaluation set
        self.model.fit(
            X_train,
            y_train,
            eval_set=[(X_train, y_train), (X_test, y_test)],
            verbose=False,
        )

        logger.info("Evaluating on %d test laps...", len(X_test))
        y_pred = self.model.predict(X_test)

        mae = mean_absolute_error(y_test, y_pred)
        rmse = root_mean_squared_error(y_test, y_pred)

        metrics = {"MAE": mae, "RMSE": rmse}
        
        logger.info("=== Evaluation Results ===")
        logger.info("MAE:  %.3f seconds", mae)
        logger.info("RMSE: %.3f seconds", rmse)

        return metrics

    def predict(self, df: pd.DataFrame) -> np.ndarray[Any, Any]:
        """Predict lap times for new data.

        Args:
            df: Gold layer DataFrame for inference.

        Returns:
            Array of predicted lap times in seconds.
        """
        X, _ = self._prepare_data(df)
        
        # Ensure feature order matches training
        missing = set(self.features) - set(X.columns)
        if missing:
            logger.warning("Missing features during inference: %s. Filling with NaN.", missing)
            for m in missing:
                X[m] = np.nan
                
        X = X[self.features]
        return self.model.predict(X)  # type: ignore[no-any-return]
