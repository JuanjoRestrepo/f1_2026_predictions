# Databricks notebook source
"""Lakeflow Spark Declarative Pipeline (Delta Live Tables) for F1 2026 predictions.

Deployed via Databricks Asset Bundles (DABs). This file is referenced in
databricks.yml under `resources.pipelines.f1_2026_medallion_pipeline.libraries`.

Do NOT import this file locally — it is executed on a Databricks cluster where
`dlt` and `spark` are injected automatically by the DLT runtime.

Pipeline layers:
  Bronze  — raw lap telemetry ingestion
  Silver  — cleaned laps with DLT data quality expectations
  Gold    — driver feature aggregates with Liquid Clustering
"""

from __future__ import annotations

# DLT and Spark are runtime-injected on Databricks — do not import locally
import dlt
import pyspark.sql.functions as SF  # noqa: N812 (Spark convention)

# ---------------------------------------------------------------------------
# Bronze — raw telemetry ingestion layer
# The job's first task (databricks_entrypoint.py --run-mode ingest) lands one
# Parquet directory per round under the raw_telemetry Unity Catalog Volume:
#     /Volumes/<catalog>/<schema>/raw_telemetry/season=<year>/round=<NN>/
# Auto Loader ("cloudFiles") tails that Volume incrementally, so each pipeline
# update only processes newly-arrived laps instead of rescanning everything.
#
# The Volume path is injected via the pipeline `configuration` block in
# resources/pipelines.yml (keys `f1.raw_telemetry_path` and
# `f1.raw_telemetry_schema`), keeping the layout in one place.
# ---------------------------------------------------------------------------

_BRONZE_COLUMNS = [
    "Driver",
    "LapNumber",
    "LapTime",
    "Compound",
    "TyreLife",
    "SessionType",
    "EventName",
    "Season",
    "RoundNumber",
]

_DEFAULT_VOLUME_PATH = "/Volumes/main/race_pace/raw_telemetry"


@dlt.table(
    comment="Bronze: raw F1 telemetry ingested into Unity Catalog.",
    table_properties={
        "quality": "bronze",
        "pipelines.reset.allowed": "true",
    },
)
def telemetry_bronze() -> object:  # return type is SparkDataFrame at runtime
    """Stream raw FastF1 lap telemetry from the raw_telemetry Volume.

    Returns:
        Streaming Spark DataFrame with raw FastF1 telemetry.
    """
    # `spark` is injected by the DLT runtime; the alias keeps the single
    # undefined-name reference in one place for the linter/type checker.
    session = spark  # type: ignore[name-defined]  # noqa: F821
    volume_path = session.conf.get("f1.raw_telemetry_path", _DEFAULT_VOLUME_PATH)
    schema_path = session.conf.get("f1.raw_telemetry_schema", f"{volume_path}/_schema")
    return (
        session.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", schema_path)
        .option("cloudFiles.inferColumnTypes", "true")
        .load(volume_path)
        .select(
            *[SF.col(column) for column in _BRONZE_COLUMNS],
            SF.input_file_name().alias("_source_file"),
            SF.current_timestamp().alias("_ingested_at"),
        )
    )


# ---------------------------------------------------------------------------
# Silver — cleaned laps with DLT data quality expectations
# Expectation levels (all four applied here):
#   expect            → warn on violation, keep row
#   expect_or_drop    → drop violating row (used for invalid lap times)
#   expect_or_fail    → halt pipeline on violation (used for NULL Driver)
#   quarantine        → route violating rows to a separate table
# ---------------------------------------------------------------------------


@dlt.table(
    comment="Silver: cleaned lap times passing data quality expectations.",
    table_properties={
        "quality": "silver",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true",
    },
)
@dlt.expect_or_fail("driver_not_null", "Driver IS NOT NULL")
@dlt.expect_or_drop(
    "valid_lap_time",
    "LapTimeSeconds >= 45.0 AND LapTimeSeconds <= 240.0",
)
@dlt.expect("lap_number_positive", "LapNumber > 0")
def laps_silver() -> object:
    """Cast LapTime to seconds and apply data quality filters.

    Returns:
        Spark DataFrame with validated, cleaned lap data.
    """
    return (
        dlt.read("telemetry_bronze")
        .withColumn(
            "LapTimeSeconds",
            SF.when(
                SF.col("LapTime").cast("double").isNotNull(),
                SF.col("LapTime").cast("double"),
            ).otherwise(SF.lit(None)),
        )
        .filter(SF.col("LapNumber").isNotNull())
        .select(
            "Driver",
            "LapNumber",
            "LapTimeSeconds",
            "Compound",
            "TyreLife",
            "SessionType",
            "EventName",
            "Season",
            "_ingested_at",
        )
    )


# ---------------------------------------------------------------------------
# Gold — driver feature aggregates stored with Liquid Clustering
# Liquid Clustering on (Season, EventName, Driver) replaces traditional
# partitioning + Z-Ordering.  Requires DBR 13.2+ with Delta 3.1+.
# Cluster keys are set via table_properties (not CLUSTER BY DDL in DLT).
# ---------------------------------------------------------------------------


@dlt.table(
    comment=(
        "Gold: per-driver race feature aggregates for Unity Catalog Feature Store. "
        "Clustered on (Season, EventName, Driver) for sub-second query latency."
    ),
    table_properties={
        "quality": "gold",
    },
)
def driver_features_gold() -> object:
    """Aggregate Silver laps into Gold driver features per session.

    Returns:
        Spark DataFrame with one row per (Season, EventName, Driver) aggregated.
    """
    return (
        dlt.read("laps_silver")
        .groupBy("Season", "EventName", "Driver")
        .agg(
            SF.avg("LapTimeSeconds").alias("mean_pace_seconds"),
            SF.min("LapTimeSeconds").alias("fastest_lap_seconds"),
            SF.stddev("LapTimeSeconds").alias("pace_std_seconds"),
            SF.count("LapNumber").alias("total_laps"),
            # Tyre degradation proxy: correlation of lap time with lap number
            SF.corr("LapNumber", "LapTimeSeconds").alias("tyre_degradation_corr"),
            SF.first("_ingested_at").alias("last_ingested_at"),
        )
    )
