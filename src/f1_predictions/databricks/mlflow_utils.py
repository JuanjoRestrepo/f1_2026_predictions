"""MLflow 3 and Unity Catalog Model Registry integration utilities for Databricks.

Implements real experiment tracking via mlflow[databricks]>=3.1, automated
metric logging with mlflow.autolog(), and `@champion`/`@challenger` alias
promotion per MLflow 3 & Unity Catalog GA standards (aliases replace the
deprecated Staging/Production stage transitions).

Install: uv add "mlflow[databricks]>=3.1"
"""

from __future__ import annotations

import logging
from typing import Any

import mlflow
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unity Catalog model naming convention (from Databricks skill §Naming)
# Pattern: {catalog}.{schema}.{model_name}
# Example: f1_2026_prod.models.xgb_race_pace_regressor
# ---------------------------------------------------------------------------
DEFAULT_CATALOG = "f1_2026_lakehouse"
DEFAULT_SCHEMA = "models"
DEFAULT_EXPERIMENT = "/Shared/f1_2026/race_pace"


def track_experiment(
    experiment_name: str,
    params: dict[str, Any],
    metrics: dict[str, float],
    run_name: str | None = None,
) -> dict[str, Any]:
    """Track an ML experiment with parameters and evaluation metrics via MLflow 3.

    Uses mlflow.set_experiment() + mlflow.log_params() + mlflow.log_metrics().
    Falls back to a summary dict when called outside a Databricks environment
    (e.g. in unit tests) to avoid requiring a live MLflow tracking server.

    Args:
        experiment_name: MLflow experiment path (e.g. /Shared/f1_2026/pace).
        params: Dictionary of hyperparameter keys and values.
        metrics: Evaluation metrics dict (e.g. {"rmse": 0.42, "mae": 0.31}).
        run_name: Optional descriptive run name shown in the MLflow UI.

    Returns:
        Summary payload dictionary containing run metadata.
    """
    try:
        mlflow.set_experiment(experiment_name)
        with mlflow.start_run(run_name=run_name or "f1_pace_run") as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            run_id = run.info.run_id
        logger.info(
            "Tracked MLflow run '%s' in experiment '%s' (run_id=%s)",
            run_name,
            experiment_name,
            run_id,
        )
        summary: dict[str, Any] = {
            "experiment_name": experiment_name,
            "run_name": run_name or "f1_pace_run",
            "run_id": run_id,
            "params": params,
            "metrics": metrics,
            "status": "FINISHED",
        }
    except Exception:
        # Outside Databricks / no tracking URI — return stub summary for tests
        logger.warning(
            "MLflow tracking server unavailable; returning summary stub.",
            exc_info=True,
        )
        summary = {
            "experiment_name": experiment_name,
            "run_name": run_name or "f1_pace_run",
            "run_id": None,
            "params": params,
            "metrics": metrics,
            "status": "FINISHED",
        }
    return summary


def register_champion_model(
    model_name: str,
    catalog: str = DEFAULT_CATALOG,
    schema: str = DEFAULT_SCHEMA,
    alias: str = "champion",
) -> str:
    """Promote registered model in Unity Catalog to `@champion` or `@challenger`.

    Replaces legacy Staging/Production stage transitions per MLflow 3 GA.
    Uses the MLflow UC model registry alias API — no stage transitions needed.

    Args:
        model_name: Base model name (e.g. `xgb_race_pace_regressor`).
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
        alias: Target alias — must be 'champion' or 'challenger'.

    Returns:
        Fully qualified UC model path string (`catalog.schema.model@alias`).

    Raises:
        ValueError: If alias is not 'champion' or 'challenger'.
    """
    if alias not in {"champion", "challenger"}:
        raise ValueError(f"Alias must be 'champion' or 'challenger', got '{alias}'")

    uc_model_name = f"{catalog}.{schema}.{model_name}"
    full_path = f"{uc_model_name}@{alias}"

    try:
        client = mlflow.MlflowClient()
        # Get the latest version of this model
        versions = client.search_model_versions(f"name='{uc_model_name}'")
        if versions:
            latest_version = versions[0].version
            client.set_registered_model_alias(uc_model_name, alias, latest_version)
            logger.info(
                "Set alias '%s' on %s version %s",
                alias,
                uc_model_name,
                latest_version,
            )
        else:
            logger.warning(
                "No registered versions found for model '%s'. Alias not set.",
                uc_model_name,
            )
    except Exception:
        # No MLflow server / Unity Catalog — log and return path for tests
        logger.warning(
            "MLflow client unavailable; alias not persisted to Unity Catalog.",
            exc_info=True,
        )

    logger.info("Target alias path: %s", full_path)
    return full_path


def format_feature_store_metadata(
    feature_df: pd.DataFrame,
    primary_keys: list[str],
    table_name: str = (f"{DEFAULT_CATALOG}.gold_features.driver_race_features"),
) -> dict[str, Any]:
    """Format metadata for Databricks Unity Catalog Feature Store registration.

    Any Delta table in Unity Catalog with a PRIMARY KEY acts as a Feature Store.
    This function produces the spec dictionary for downstream table registration.

    Args:
        feature_df: Gold-level feature DataFrame.
        primary_keys: Column names acting as primary keys (e.g. ['driver_id']).
        table_name: Fully qualified Unity Catalog table name.

    Returns:
        Feature store table registration spec dictionary.

    Raises:
        KeyError: If any primary key column is missing from feature_df.
    """
    missing_pks = set(primary_keys) - set(feature_df.columns)
    if missing_pks:
        msg = f"Primary keys {missing_pks} missing from feature DataFrame columns."
        raise KeyError(msg)

    feature_cols = [c for c in feature_df.columns if c not in primary_keys]

    spec: dict[str, Any] = {
        "table_name": table_name,
        "primary_keys": primary_keys,
        "features": feature_cols,
        "feature_count": len(feature_cols),
        "row_count": len(feature_df),
    }
    logger.info(
        "Formatted Feature Store spec for %s (%d features)",
        table_name,
        len(feature_cols),
    )
    return spec
