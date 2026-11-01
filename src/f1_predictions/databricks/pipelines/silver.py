"""Silver-layer transforms shared by the DLT pipeline and local Spark tests.

The pipeline notebook cannot be imported locally (``dlt`` and ``spark`` are
runtime-injected), so the pure DataFrame logic lives here where tests can
exercise it against a local Spark session.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as SF  # noqa: N812 (Spark convention)

# A lap is uniquely identified by the round it belongs to plus the driver and
# the lap number. Season is part of the key because round numbers repeat.
LAP_NATURAL_KEY: tuple[str, ...] = ("Season", "RoundNumber", "Driver", "LapNumber")


def dedupe_laps(laps: DataFrame) -> DataFrame:
    """Keep the most recently ingested copy of each lap.

    The ingest task overwrites a round's Parquet directory, but Bronze is an
    append-only streaming table: re-running the same round appends a second
    copy of every lap. Deduplicate on the natural key, preferring the newest
    ``_ingested_at`` so a corrected re-ingest replaces the stale copy instead
    of being dropped.

    Args:
        laps: Bronze rows with ``_ingested_at`` and the natural-key columns.

    Returns:
        One row per ``(Season, RoundNumber, Driver, LapNumber)``.
    """
    latest = Window.partitionBy(*LAP_NATURAL_KEY).orderBy(SF.col("_ingested_at").desc())
    return (
        laps.withColumn("_dedupe_rank", SF.row_number().over(latest))
        .filter(SF.col("_dedupe_rank") == 1)
        .drop("_dedupe_rank")
    )
