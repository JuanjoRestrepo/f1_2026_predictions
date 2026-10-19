"""Spark implementation of the shared lap-level feature contract (Task 21.3).

This module is imported by the DLT notebook (``f1_medallion_pipeline.py``) and
by the local Spark parity test. It is deliberately Spark-only: the Pandas
reference lives in :mod:`f1_predictions.features.rolling_pace` and
``tests/unit/test_lap_features_spark.py`` compares the two row for row.

Causality is the point of the module. Every rolling window ends at row ``-1``
(the previous lap), ``delta_to_fastest_s`` uses a cumulative minimum of prior
laps, and the table carries no position, sector, speed or full-stint aggregate.
See :mod:`f1_predictions.features.contract` for why those columns are excluded.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pyspark.sql.functions as SF  # noqa: N812 (Spark convention)
from pyspark.sql import DataFrame, Window

# The DLT notebook imports this file as a top-level sibling module, so the
# project's ``src`` root is not automatically on sys.path. Resolve it from this
# file's location (``.../src/f1_predictions/databricks/pipelines/lap_features.py``).
_SRC_ROOT = Path(__file__).resolve().parents[3]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from f1_predictions.features.contract import (  # noqa: E402
    FEATURE_CONTRACT_VERSION,
    LAP_CONTEXT_COLUMNS,
    LAP_FEATURES,
    LAP_KEYS,
    LAP_TARGET,
    VERSION_COLUMN,
)

_STINT_PARTITION = ("Season", "RoundNumber", "Driver", "Stint")
_DRIVER_SESSION_PARTITION = ("Season", "RoundNumber", "Driver")
_COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET")


def _with_rolling_pace(base: DataFrame) -> DataFrame:
    """Add causal 3/5-lap pace windows and their difference.

    Spark's ``avg``/``stddev`` ignore nulls and shrink to the available rows,
    which matches Pandas ``rolling(..., min_periods=1)`` for the means. The
    standard deviation needs a count guard to match Pandas ``min_periods=2``.
    """
    stint_order = Window.partitionBy(*_STINT_PARTITION).orderBy("LapNumber")
    previous_3 = stint_order.rowsBetween(-3, -1)
    previous_5 = stint_order.rowsBetween(-5, -1)

    return (
        base.withColumn("roll_laptime_3", SF.avg(LAP_TARGET).over(previous_3))
        .withColumn("roll_laptime_5", SF.avg(LAP_TARGET).over(previous_5))
        .withColumn(
            "roll_std_3",
            SF.when(
                SF.count(LAP_TARGET).over(previous_3) >= 2,
                SF.stddev(LAP_TARGET).over(previous_3),
            ),
        )
        .withColumn(
            "delta_roll_pace",
            SF.col("roll_laptime_3") - SF.col("roll_laptime_5"),
        )
    )


def _with_delta_to_fastest(base: DataFrame) -> DataFrame:
    """Add the gap to the driver's best *previously completed* lap."""
    prior_laps = (
        Window.partitionBy(*_DRIVER_SESSION_PARTITION)
        .orderBy("LapNumber")
        .rowsBetween(Window.unboundedPreceding, -1)
    )
    return base.withColumn(
        "delta_to_fastest_s",
        SF.col(LAP_TARGET) - SF.min(LAP_TARGET).over(prior_laps),
    )


def _with_compound_indicators(base: DataFrame) -> DataFrame:
    """Add the five dry/wet compound indicators used by the local encoder."""
    compound = SF.upper(SF.trim(SF.col("Compound")))
    for name in _COMPOUNDS:
        base = base.withColumn(
            f"Compound_{name}",
            SF.when(compound == name, SF.lit(1.0)).otherwise(SF.lit(0.0)),
        )
    return base


def build_lap_features_gold(silver: DataFrame) -> DataFrame:
    """Build the per-lap Gold table from DLT ``laps_silver``.

    Rows are restricted to race sessions with a non-null lap number and stint.
    A lap without a stint has no meaningful rolling-pace group, and a lap
    without a number cannot be ordered or keyed; both are excluded explicitly
    rather than letting Spark group null keys together. Casting before the
    filter also turns NaN (from a legacy float column) into NULL.

    Args:
        silver: ``laps_silver`` Spark DataFrame containing ``LapTimeSeconds``,
            ``Stint``, ``Compound``, ``Team`` and ``Position``.

    Returns:
        Spark DataFrame with the contract keys, context columns, target,
        13 pre-lap features and ``feature_contract_version``.
    """
    base = (
        silver.filter(SF.col("SessionType") == "Race")
        .withColumn("LapNumber", SF.col("LapNumber").cast("int"))
        .withColumn("Stint", SF.col("Stint").cast("int"))
        .filter(SF.col("LapNumber").isNotNull())
        .filter(SF.col("Stint").isNotNull())
        .withColumn("TyreLife", SF.col("TyreLife").cast("double"))
        .withColumn("Position", SF.col("Position").cast("int"))
        .withColumn("Team", SF.col("Team").cast("string"))
        .withColumn("Compound", SF.col("Compound").cast("string"))
        .withColumn(LAP_TARGET, SF.col("LapTimeSeconds").cast("double"))
    )

    base = _with_rolling_pace(base)
    base = _with_delta_to_fastest(base)
    base = _with_compound_indicators(base)

    ordered = list(
        dict.fromkeys(
            [
                *LAP_KEYS,
                *LAP_CONTEXT_COLUMNS,
                LAP_TARGET,
                *LAP_FEATURES,
                VERSION_COLUMN,
            ]
        )
    )
    return base.withColumn(VERSION_COLUMN, SF.lit(FEATURE_CONTRACT_VERSION)).select(
        *ordered
    )
