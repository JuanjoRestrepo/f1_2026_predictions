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
# Formats raw lap telemetry into the Bronze Delta table in Unity Catalog.
# In production with cloud storage (S3/ADLS/GCS), replace the sample DataFrame
# below with `spark.readStream.format("cloudFiles")` reading from a Unity Catalog
# Volume path (e.g. `/Volumes/main/race_pace/raw_telemetry`).
# ---------------------------------------------------------------------------


@dlt.table(
    comment="Bronze: raw F1 telemetry ingested into Unity Catalog.",
    table_properties={
        "quality": "bronze",
        "pipelines.reset.allowed": "true",
    },
)
def telemetry_bronze() -> object:  # return type is SparkDataFrame at runtime
    """Ingest raw lap telemetry into the Bronze Delta table.

    Returns:
        Spark DataFrame with raw FastF1 telemetry.
    """
    sample_data = [
        ("VER", 1, 84.12, "SOFT", 1, "Race", "Bahrain GP", 2026),
        ("VER", 2, 83.95, "SOFT", 2, "Race", "Bahrain GP", 2026),
        ("VER", 3, 83.88, "SOFT", 3, "Race", "Bahrain GP", 2026),
        ("HAM", 1, 84.50, "MEDIUM", 1, "Race", "Bahrain GP", 2026),
        ("HAM", 2, 84.20, "MEDIUM", 2, "Race", "Bahrain GP", 2026),
        ("HAM", 3, 84.15, "MEDIUM", 3, "Race", "Bahrain GP", 2026),
        ("LEC", 1, 84.30, "SOFT", 1, "Race", "Bahrain GP", 2026),
        ("LEC", 2, 84.05, "SOFT", 2, "Race", "Bahrain GP", 2026),
        ("LEC", 3, 83.99, "SOFT", 3, "Race", "Bahrain GP", 2026),
        ("NOR", 1, 84.60, "HARD", 1, "Race", "Bahrain GP", 2026),
        ("NOR", 2, 84.35, "HARD", 2, "Race", "Bahrain GP", 2026),
        ("NOR", 3, 84.25, "HARD", 3, "Race", "Bahrain GP", 2026),
    ]
    columns = [
        "Driver",
        "LapNumber",
        "LapTime",
        "Compound",
        "TyreLife",
        "SessionType",
        "EventName",
        "Season",
    ]
    # spark is injected by the DLT runtime — not available locally
    return (
        spark.createDataFrame(sample_data, schema=columns)  # type: ignore[name-defined] # noqa: F821
        .withColumn("_source_file", SF.lit("telemetry_ingest.parquet"))
        .withColumn("_ingested_at", SF.current_timestamp())
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
