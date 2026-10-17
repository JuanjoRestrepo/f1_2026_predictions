"""Databricks Lakehouse integration package for F1 2026 predictions.

Includes Lakeflow Spark Declarative Pipelines (Medallion architecture),
Unity Catalog Feature Store contracts, and MLflow 3 model tracking/governance.
"""

from f1_predictions.databricks.medallion import (
    compute_gold_driver_features,
    process_bronze_telemetry,
    process_silver_laps,
)
from f1_predictions.databricks.mlflow_utils import (
    get_champion_metric,
    register_champion_model,
    should_promote,
    track_experiment,
)
from f1_predictions.databricks.volume_ingest import (
    BRONZE_LAP_COLUMNS,
    build_bronze_laps,
    completed_round_numbers,
    round_volume_path,
    schema_location,
    volume_root,
)

__all__ = [
    "BRONZE_LAP_COLUMNS",
    "build_bronze_laps",
    "completed_round_numbers",
    "compute_gold_driver_features",
    "get_champion_metric",
    "process_bronze_telemetry",
    "process_silver_laps",
    "register_champion_model",
    "round_volume_path",
    "schema_location",
    "should_promote",
    "track_experiment",
    "volume_root",
]
