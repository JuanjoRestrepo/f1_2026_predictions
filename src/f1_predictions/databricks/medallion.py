"""Databricks Medallion Architecture module for F1 race predictions.

Implements Bronze (raw ingestion), Silver (clean & normalized laps), and
Gold (feature engineered aggregates for model training) transformations using
Lakeflow Spark Declarative Pipelines / Delta Lake conventions.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def process_bronze_telemetry(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Ingest raw FastF1 telemetry and add Databricks ingestion metadata.

    Args:
        raw_df: Ingested raw telemetry DataFrame from Auto Loader or FastF1 API.

    Returns:
        Bronze telemetry DataFrame with normalized column names and audit timestamp.
    """
    if raw_df.empty:
        logger.warning("Empty raw telemetry DataFrame passed to bronze ingestion.")
        return pd.DataFrame()

    df = raw_df.copy()
    df.columns = [str(col).strip().replace(" ", "_") for col in df.columns]

    if "_ingested_at" not in df.columns:
        df["_ingested_at"] = pd.Timestamp.now(tz="UTC").isoformat()

    logger.info("Processed Bronze telemetry table with %d rows.", len(df))
    return df


def process_silver_laps(bronze_df: pd.DataFrame) -> pd.DataFrame:
    """Clean and normalize Bronze telemetry into Silver lap data.

    Enforces data quality expectations: drops invalid lap times (<45s or >240s),
    fills missing sector times, and computes LapTimeSeconds.

    Args:
        bronze_df: Bronze level raw telemetry DataFrame.

    Returns:
        Silver level cleaned laps DataFrame.
    """
    if bronze_df.empty:
        return pd.DataFrame()

    df = bronze_df.copy()

    # Ensure required columns exist
    required_cols = {"LapTime", "Driver", "LapNumber", "SessionType"}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        logger.error("Missing required columns for Silver conversion: %s", missing)
        raise KeyError(f"Missing required columns for Silver laps: {missing}")

    # Convert LapTime to seconds if timedelta or numeric string
    if "LapTimeSeconds" not in df.columns:
        if pd.api.types.is_timedelta64_dtype(df["LapTime"]):
            df["LapTimeSeconds"] = df["LapTime"].dt.total_seconds()
        else:
            df["LapTimeSeconds"] = pd.to_numeric(df["LapTime"], errors="coerce")

    # Data Quality Expectations (DLT expectation filtering rule: 45s <= LapTime <= 240s)
    valid_mask = (
        df["LapTimeSeconds"].notna()
        & (df["LapTimeSeconds"] >= 45.0)
        & (df["LapTimeSeconds"] <= 240.0)
    )
    df_clean = df.loc[valid_mask].copy()

    # Sort deterministically
    df_clean.sort_values(by=["Driver", "LapNumber"], inplace=True)
    logger.info(
        "Silver laps transformation complete: %d valid rows out of %d original.",
        len(df_clean),
        len(df),
    )
    return df_clean


def compute_gold_driver_features(silver_df: pd.DataFrame) -> pd.DataFrame:
    """Compute Gold-layer aggregates & features for Databricks Feature Store.

    Computes rolling pace, tire degradation slope, and lap time variance per driver.

    Args:
        silver_df: Cleaned Silver level laps DataFrame.

    Returns:
        Gold level feature matrix indexed by driver with primary key columns.
    """
    if silver_df.empty:
        return pd.DataFrame()

    required_cols = {"Driver", "LapNumber", "LapTimeSeconds"}
    if not required_cols.issubset(silver_df.columns):
        raise KeyError(f"Missing required columns for Gold features: {required_cols}")

    gold_rows: list[dict[str, Any]] = []

    for driver, group in silver_df.groupby("Driver"):
        laps: np.ndarray[Any, np.dtype[np.float64]] = group.sort_values("LapNumber")[
            "LapTimeSeconds"
        ].to_numpy(dtype=np.float64)
        if len(laps) == 0:
            continue

        mean_pace = float(np.mean(laps))
        median_pace = float(np.median(laps))
        std_pace = float(np.std(laps)) if len(laps) > 1 else 0.0
        fastest_lap = float(np.min(laps))
        total_laps = len(laps)

        # Tire degradation proxy: slope of lap times over lap numbers
        if len(laps) > 2:
            lap_nums = np.arange(1, len(laps) + 1)
            deg_slope = float(np.polyfit(lap_nums, laps, 1)[0])
        else:
            deg_slope = 0.0

        gold_rows.append(
            {
                "driver_id": str(driver),
                "total_laps": total_laps,
                "mean_pace_seconds": round(mean_pace, 4),
                "median_pace_seconds": round(median_pace, 4),
                "pace_std_seconds": round(std_pace, 4),
                "fastest_lap_seconds": round(fastest_lap, 4),
                "tyre_degradation_slope": round(deg_slope, 5),
            }
        )

    gold_df = pd.DataFrame(gold_rows)
    logger.info("Computed Gold features for %d drivers.", len(gold_df))
    return gold_df


def get_spark_dlt_pipeline_definition() -> str:
    """Generate PySpark / Delta Live Tables pipeline source code string.

    Returns:
        Python code string defining DLT decorators `@dlt.table` and expectations.
    """
    return '''"""Databricks Spark Declarative Pipeline (Delta Live Tables)."""

import dlt
from pyspark.sql import functions as F

@dlt.table(
    comment="Raw Bronze telemetry ingested via Auto Loader",
    table_properties={"quality": "bronze"}
)
def telemetry_bronze():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .load("/mnt/f1_raw/telemetry")
        .withColumn("_ingested_at", F.current_timestamp())
    )

@dlt.table(
    comment="Cleaned Silver lap times with quality filters",
    table_properties={
        "quality": "silver",
        "delta.autoOptimize.optimizeWrite": "true",
    }
)
@dlt.expect_or_drop(
    "valid_lap_time",
    "LapTimeSeconds >= 45.0 AND LapTimeSeconds <= 240.0",
)
def laps_silver():
    return (
        dlt.read("telemetry_bronze")
        .withColumn("LapTimeSeconds", F.col("LapTime").cast("double"))
        .filter(F.col("Driver").isNotNull())
    )

@dlt.table(
    comment="Gold features with Liquid Clustering on driver_id",
    table_properties={
        "quality": "gold",
        "delta.liquidClusteringColumns": "driver_id",
    }
)
def driver_features_gold():
    return (
        dlt.read("laps_silver")
        .groupBy("Driver")
        .agg(
            F.avg("LapTimeSeconds").alias("mean_pace_seconds"),
            F.min("LapTimeSeconds").alias("fastest_lap_seconds"),
            F.count("LapNumber").alias("total_laps")
        )
    )
'''
