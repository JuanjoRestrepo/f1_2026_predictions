"""Spark/Pandas parity for the shared lap feature contract (Task 21.3).

The DLT table is built by Spark, but the published/local reference is Pandas.
This test runs both implementations on the same synthetic laps and compares the
shared feature matrix row for row, including the causal first-lap NaNs, the
3-lap standard-deviation minimum, compound indicators and cross-event isolation.

PySpark is an optional local dependency. CI skips the module when it is absent;
run it locally with ``uv pip install pyspark``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
import pytest

pytest.importorskip("pyspark")

from pyspark.sql import SparkSession

from f1_predictions.databricks.pipelines.lap_features import (
    build_lap_features_gold,
)
from f1_predictions.features.contract import (
    FEATURE_CONTRACT_VERSION,
    LAP_FEATURES,
    LAP_KEYS,
    LAP_TARGET,
    VERSION_COLUMN,
)
from f1_predictions.features.rolling_pace import (
    add_lap_delta_to_fastest,
    add_rolling_pace_features,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET")


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    """Start one local Spark session for the parity test."""
    session = (
        SparkSession.builder.master("local[2]")
        .appName("f1-lap-feature-parity")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.driver.memory", "1g")
        .getOrCreate()
    )
    yield session
    session.stop()


def _synthetic_laps() -> pd.DataFrame:
    """Two events, two drivers, two stints, plus non-race and null-stint rows."""
    records: list[dict[str, object]] = []
    events = [
        (3, "Japanese Grand Prix", 0.0),
        (4, "Bahrain Grand Prix", 1.0),
    ]
    drivers = [("VER", "Red Bull", 0.0), ("NOR", "McLaren", 0.3)]

    for round_number, event_name, event_offset in events:
        lap_number = 1
        for driver, team, driver_offset in drivers:
            for stint, (compound, stint_offset) in enumerate(
                [("SOFT", 0.0), ("MEDIUM", 0.5)],
                start=1,
            ):
                for tyre_life in range(1, 6):
                    lap_time = (
                        90.0
                        + event_offset
                        + driver_offset
                        + stint_offset
                        + 0.06 * tyre_life
                        + 0.01 * lap_number
                    )
                    records.append(
                        {
                            "Season": 2026,
                            "RoundNumber": round_number,
                            "EventName": event_name,
                            "Driver": driver,
                            "LapNumber": lap_number,
                            "Stint": stint,
                            "TyreLife": (
                                None
                                if (driver == "VER" and stint == 1 and lap_number == 3)
                                else float(tyre_life)
                            ),
                            "Compound": compound,
                            "Team": team,
                            "Position": 1 if driver == "VER" else 2,
                            "SessionType": "Race",
                            "LapTime_s": lap_time,
                            "LapTimeSeconds": lap_time,
                        }
                    )
                    lap_number += 1

        # A qualifying row and a race row without a stint must both be excluded.
        for session_type, stint in (("Qualifying", 1), ("Race", None)):
            lap_time = 89.0 + event_offset
            records.append(
                {
                    "Season": 2026,
                    "RoundNumber": round_number,
                    "EventName": event_name,
                    "Driver": "VER",
                    "LapNumber": lap_number,
                    "Stint": stint,
                    "TyreLife": 1.0,
                    "Compound": "SOFT",
                    "Team": "Red Bull",
                    "Position": 1,
                    "SessionType": session_type,
                    "LapTime_s": lap_time,
                    "LapTimeSeconds": lap_time,
                }
            )
            lap_number += 1

        # A race row without a lap number cannot be keyed or ordered either.
        records.append(
            {
                "Season": 2026,
                "RoundNumber": round_number,
                "EventName": event_name,
                "Driver": "VER",
                "LapNumber": None,
                "Stint": 1,
                "TyreLife": 1.0,
                "Compound": "SOFT",
                "Team": "Red Bull",
                "Position": 1,
                "SessionType": "Race",
                "LapTime_s": 89.0 + event_offset,
                "LapTimeSeconds": 89.0 + event_offset,
            }
        )

    return pd.DataFrame(records)


def _pandas_reference(frame: pd.DataFrame) -> pd.DataFrame:
    """Run the local feature functions once per event, as the pipeline does."""
    race = frame[
        (frame["SessionType"] == "Race")
        & frame["Stint"].notna()
        & frame["LapNumber"].notna()
    ].copy()
    references: list[pd.DataFrame] = []
    for _, group in race.groupby(
        ["Season", "RoundNumber", "EventName"],
        sort=False,
    ):
        enriched = add_rolling_pace_features(group.copy())
        enriched = add_lap_delta_to_fastest(enriched)
        for compound in _COMPOUNDS:
            enriched[f"Compound_{compound}"] = (
                enriched["Compound"].str.upper().eq(compound).astype(float)
            )
        references.append(enriched)
    return pd.concat(references, ignore_index=True)


def test_spark_lap_features_match_pandas_reference(spark: SparkSession) -> None:
    """Every shared feature must agree with the local implementation."""
    frame = _synthetic_laps()
    reference = _pandas_reference(frame)

    actual = build_lap_features_gold(spark.createDataFrame(frame)).toPandas()

    columns = list(dict.fromkeys([*LAP_KEYS, LAP_TARGET, *LAP_FEATURES]))
    expected = reference.sort_values(list(LAP_KEYS)).reset_index(drop=True)
    observed = actual.sort_values(list(LAP_KEYS)).reset_index(drop=True)

    assert len(observed) == len(expected)
    pd.testing.assert_frame_equal(
        observed.loc[:, columns],
        expected.loc[:, columns],
        check_dtype=False,
        rtol=1e-9,
        atol=1e-9,
    )
    assert set(actual[VERSION_COLUMN]) == {FEATURE_CONTRACT_VERSION}
    assert actual["SessionType"].eq("Race").all()
    assert actual["LapNumber"].notna().all()
    assert actual["Stint"].notna().all()
