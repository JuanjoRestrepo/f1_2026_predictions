"""FastAPI entry point for the F1 2026 Pace Predictor."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from f1_predictions.models.base import BasePaceRegressor
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# Global model instance
model: BasePaceRegressor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load the ML model on startup and clean up on shutdown."""
    global model
    settings = get_settings()
    model_path = settings.data_outputs_dir / "models" / "xgb_pace_model.joblib"

    try:
        # Load the base class using classmethod
        from f1_predictions.models.xgboost_pipeline import (
            F1PaceRegressor,
        )

        model = F1PaceRegressor.load_from_path(model_path)
        logger.info("Successfully loaded XGBoost model for API serving.")
    except Exception as e:
        logger.exception("Failed to load model from %s", model_path)
        # Crash the container if model is missing (MLOps standard)
        raise RuntimeError(f"CRITICAL: ML Model not found at {model_path}") from e

    yield
    # Cleanup on shutdown (if any)
    logger.info("Shutting down API. Cleaning up resources.")


app = FastAPI(
    title="F1 2026 Pace Predictor API",
    description=(
        "REST API for predicting F1 lap times based on "
        "telemetric and environmental features."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


class PredictionRequest(BaseModel):
    """Payload containing lap features.

    Accepts arbitrary extra fields to accommodate all one-hot encoded
    and engineered columns present in the Gold layer.
    """

    features: list[dict[str, Any]] = Field(
        ...,
        description="List of feature dictionaries. Each dictionary represents one lap.",
        json_schema_extra={
            "example": [
                {
                    "Compound_SOFT": 1.0,
                    "Compound_MEDIUM": 0.0,
                    "Compound_HARD": 0.0,
                    "TrackTemp": 45.2,
                    "TyreLife": 12,
                    "Track_Evolution_Factor": -0.5,
                    "Brake_Wear_Proxy": 0.02,
                }
            ]
        },
    )


class PredictionResponse(BaseModel):
    """Response containing the list of predicted lap times."""

    predictions: list[float]
    model_features_expected: int


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Check API and Model health."""
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")
    return {
        "status": "ok",
        "model_loaded": True,
        "features_count": str(len(model.features)),
    }


@app.post("/predict", response_model=PredictionResponse)
async def predict(payload: PredictionRequest) -> PredictionResponse:
    """Predict lap times for a batch of feature sets."""
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")

    try:
        # Convert incoming JSON dicts to a pandas DataFrame
        df = pd.DataFrame(payload.features)

        # Predict using the loaded model wrapper
        # The wrapper's predict() method handles feature reindexing and missing columns
        predictions = model.predict(df)

        return PredictionResponse(
            predictions=predictions.tolist(),
            model_features_expected=len(model.features),
        )
    except Exception as e:
        logger.exception("Prediction failed")
        raise HTTPException(status_code=400, detail=str(e)) from e
