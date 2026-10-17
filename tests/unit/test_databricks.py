"""Unit tests for the Databricks Lakehouse integration module."""

from __future__ import annotations

import pandas as pd
import pytest

from f1_predictions.databricks.medallion import (
    compute_gold_driver_features,
    get_spark_dlt_pipeline_definition,
    process_bronze_telemetry,
    process_silver_laps,
)
from f1_predictions.databricks.mlflow_utils import (
    format_feature_store_metadata,
    get_champion_metric,
    register_champion_model,
    should_promote,
    track_experiment,
)


def test_process_bronze_telemetry_adds_ingested_at() -> None:
    """Bronze ingestion should add _ingested_at audit column and normalize names."""
    raw = pd.DataFrame({"Lap Time": [90.5, 91.2], "Driver Name": ["VER", "NOR"]})
    bronze = process_bronze_telemetry(raw)

    assert "_ingested_at" in bronze.columns
    assert "Lap_Time" in bronze.columns
    assert len(bronze) == 2


def test_process_silver_laps_filters_out_of_bound_laps() -> None:
    """Silver pipeline should drop invalid lap times (<45s or >240s)."""
    bronze = pd.DataFrame(
        {
            "LapTime": [90.0, 30.0, 300.0, 88.5],
            "Driver": ["VER", "VER", "NOR", "NOR"],
            "LapNumber": [1, 2, 3, 4],
            "SessionType": ["Race", "Race", "Race", "Race"],
        }
    )
    silver = process_silver_laps(bronze)

    assert len(silver) == 2
    assert set(silver["Driver"]) == {"VER", "NOR"}
    assert list(silver["LapTimeSeconds"]) == [88.5, 90.0]


def test_compute_gold_driver_features_calculates_aggregates() -> None:
    """Gold layer should compute rolling pace, fastest lap, and deg slope."""
    silver = pd.DataFrame(
        {
            "Driver": ["VER", "VER", "VER", "NOR", "NOR"],
            "LapNumber": [1, 2, 3, 1, 2],
            "LapTimeSeconds": [90.0, 91.0, 92.0, 89.0, 89.5],
        }
    )
    gold = compute_gold_driver_features(silver)

    assert len(gold) == 2
    ver_row = gold.loc[gold["driver_id"] == "VER"].iloc[0]
    assert ver_row["total_laps"] == 3
    assert ver_row["fastest_lap_seconds"] == 90.0
    assert ver_row["tyre_degradation_slope"] > 0  # Pace slowing down


def test_track_experiment_returns_summary() -> None:
    """MLflow track_experiment helper should return structured summary payload."""
    summary = track_experiment(
        experiment_name="/Shared/f1_2026/pace",
        params={"n_estimators": 100, "max_depth": 5},
        metrics={"rmse": 0.42, "mae": 0.31},
        run_name="monaco_gp_test",
    )
    assert summary["experiment_name"] == "/Shared/f1_2026/pace"
    assert summary["metrics"]["rmse"] == 0.42
    assert summary["status"] == "FINISHED"


def test_register_champion_model_returns_unity_catalog_path() -> None:
    """Unity Catalog model registration should format champion alias path."""
    path = register_champion_model("xgb_race_pace", alias="champion")
    assert path == "f1_2026_lakehouse.models.xgb_race_pace@champion"

    with pytest.raises(ValueError, match="Alias must be 'champion' or 'challenger'"):
        register_champion_model("xgb_race_pace", alias="invalid_alias")


def test_format_feature_store_metadata_generates_spec() -> None:
    """Feature store spec helper should structure table and PK metadata."""
    df = pd.DataFrame(
        {
            "driver_id": ["VER", "HAM"],
            "mean_pace_seconds": [90.2, 90.5],
            "tyre_degradation_slope": [0.05, 0.04],
        }
    )
    spec = format_feature_store_metadata(df, primary_keys=["driver_id"])

    assert spec["primary_keys"] == ["driver_id"]
    assert spec["feature_count"] == 2
    assert "mean_pace_seconds" in spec["features"]


def test_get_spark_dlt_pipeline_definition_returns_valid_python_str() -> None:
    """DLT template function should return Python code containing dlt decorators."""
    code = get_spark_dlt_pipeline_definition()
    assert "@dlt.table" in code
    assert "telemetry_bronze" in code
    assert "liquidClusteringColumns" in code


def test_should_promote_without_incumbent() -> None:
    """First-ever training has no incumbent, so the candidate is promoted."""
    assert should_promote(0.42, None) is True


def test_should_promote_on_improvement() -> None:
    """A strictly lower metric beats the incumbent."""
    assert should_promote(0.30, 0.42) is True


def test_should_not_promote_on_regression() -> None:
    """A higher metric never replaces the incumbent."""
    assert should_promote(0.55, 0.42) is False


def test_should_not_promote_on_tie() -> None:
    """Ties keep the incumbent (only measurable improvement promotes)."""
    assert should_promote(0.42, 0.42) is False


def test_should_promote_respects_tolerance() -> None:
    """A marginal improvement below the tolerance does not promote."""
    assert should_promote(0.415, 0.42, tolerance=0.01) is False
    assert should_promote(0.40, 0.42, tolerance=0.01) is True


def test_should_promote_rejects_negative_tolerance() -> None:
    """A negative tolerance is a configuration error."""
    with pytest.raises(ValueError, match="tolerance must be non-negative"):
        should_promote(0.30, 0.42, tolerance=-0.1)


def test_get_champion_metric_returns_none_without_registry() -> None:
    """Offline (no MLflow registry) the incumbent metric degrades to None."""
    assert get_champion_metric("main", "race_pace", "xgb_race_pace") is None
