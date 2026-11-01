"""Silver dedupe: a re-ingested round must not double-count laps.

Bronze is an append-only streaming table, while the ingest task overwrites the
round's Parquet directory. Re-running a round therefore appends a second copy
of every lap, which used to double ``total_laps`` and skew the Gold features.
``dedupe_laps`` keeps the most recently ingested copy per natural key.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

pytest.importorskip("pyspark")

from pyspark.sql import DataFrame, SparkSession

from f1_predictions.databricks.pipelines.silver import dedupe_laps

_SCHEMA = (
    "Driver string, LapNumber int, LapTimeSeconds double, "
    "_ingested_at timestamp, Season int, RoundNumber int"
)


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    """Start one local Spark session for the dedupe tests."""
    session = (
        SparkSession.builder.master("local[2]")
        .appName("f1-silver-dedupe")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.driver.memory", "1g")
        .getOrCreate()
    )
    yield session
    session.stop()


def _frame(spark: SparkSession) -> DataFrame:
    """Two copies of one lap, a distinct lap, and the same lap last season."""
    rows = [
        # Pre-race stub written at 06:01 UTC.
        ("VER", 2, 80.0, datetime(2026, 11, 1, 6, 1, tzinfo=UTC), 2026, 19),
        # Re-ingest after the race: same key, newer timestamp wins.
        ("VER", 2, 79.5, datetime(2026, 11, 1, 22, 45, tzinfo=UTC), 2026, 19),
        ("VER", 3, 79.8, datetime(2026, 11, 1, 22, 45, tzinfo=UTC), 2026, 19),
        # Same driver and lap number in another season is a different lap.
        ("VER", 2, 78.0, datetime(2025, 10, 26, 22, 0, tzinfo=UTC), 2025, 19),
    ]
    return spark.createDataFrame(rows, _SCHEMA)


def test_keeps_the_latest_copy_per_natural_key(spark: SparkSession) -> None:
    """The newer ingest replaces the stub instead of being dropped."""
    rows = {
        (row.Season, row.RoundNumber, row.Driver, row.LapNumber): row.LapTimeSeconds
        for row in dedupe_laps(_frame(spark)).collect()
    }

    assert len(rows) == 3
    assert rows[(2026, 19, "VER", 2)] == 79.5
    assert rows[(2026, 19, "VER", 3)] == 79.8
    assert rows[(2025, 19, "VER", 2)] == 78.0


def test_is_idempotent(spark: SparkSession) -> None:
    """Deduping an already-deduped frame changes nothing."""
    once = dedupe_laps(_frame(spark))
    twice = dedupe_laps(once)

    assert twice.count() == once.count()
