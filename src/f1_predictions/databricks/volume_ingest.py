"""Unity Catalog Volume ingestion helpers for the F1 2026 Bronze layer.

This module bridges the *real* FastF1 ingestion path (local ``scripts/``
pipeline) and the *cloud* Databricks medallion pipeline. The Lakeflow job's
first task runs ``databricks_entrypoint.py --run-mode ingest``: it loads the
just-completed round via FastF1, reshapes the laps DataFrame onto the Bronze
contract below, and writes Parquet into a Unity Catalog Volume. The DLT
pipeline then tails that Volume with Auto Loader (``cloudFiles``).

Design rationale:
    - The transform is a *pure* function (``build_bronze_laps``) so it can be
      unit-tested without Spark, a Databricks workspace, or the FastF1 network.
    - The Bronze column contract is defined once here and imported by both the
      writer (entry point) and, conceptually, the DLT Bronze table reader.
    - Path helpers centralise the Volume layout so the writer and the reader
      can never drift apart.

Layout written to the Volume::

    /Volumes/<catalog>/<schema>/raw_telemetry/
        season=<year>/round=<NN>/   # one Parquet directory per round
        _schema/                    # Auto Loader schema location
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final, cast

import pandas as pd

# ---------------------------------------------------------------------------
# Bronze contract
# ---------------------------------------------------------------------------
# The exact column names the DLT ``telemetry_bronze`` table selects. Keeping
# this as a single source of truth prevents silent writer/reader drift.
BRONZE_LAP_COLUMNS: Final[tuple[str, ...]] = (
    "Driver",
    "LapNumber",
    "LapTime",
    "Compound",
    "TyreLife",
    "Stint",
    "Team",
    "Position",
    "SessionType",
    "EventName",
    "Season",
    "RoundNumber",
)

# Columns that MUST be present on the incoming FastF1 laps frame. The rest are
# synthesised (metadata) or defaulted to NULL when absent.
_REQUIRED_SOURCE_COLUMNS: Final[tuple[str, ...]] = ("Driver", "LapNumber", "LapTime")


# ---------------------------------------------------------------------------
# Path helpers — the single source of truth for the Volume layout
# ---------------------------------------------------------------------------


def volume_root(catalog: str, schema: str) -> str:
    """Return the root Volume path for raw telemetry.

    Args:
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.

    Returns:
        Absolute Volume path, e.g. ``/Volumes/main/race_pace/raw_telemetry``.
    """
    return f"/Volumes/{catalog}/{schema}/raw_telemetry"


def round_volume_path(
    catalog: str,
    schema: str,
    season: int,
    round_number: int,
) -> str:
    """Return the per-round Parquet directory inside the telemetry Volume.

    The ``season=…/round=…`` Hive-style layout lets Auto Loader and ad-hoc SQL
    prune by partition without scanning the whole Volume.

    Args:
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.
        season: F1 season year.
        round_number: Round number within the season.

    Returns:
        Absolute Volume path for the round's laps Parquet files.
    """
    return f"{volume_root(catalog, schema)}/season={season}/round={round_number:02d}"


def schema_location(catalog: str, schema: str) -> str:
    """Return the Auto Loader schema-inference directory for the Volume.

    Args:
        catalog: Unity Catalog catalog name.
        schema: Unity Catalog schema name.

    Returns:
        Absolute Volume path for the ``cloudFiles.schemaLocation``.
    """
    return f"{volume_root(catalog, schema)}/_schema"


# ---------------------------------------------------------------------------
# Round resolution
# ---------------------------------------------------------------------------


def completed_round_numbers(
    schedule: pd.DataFrame,
    now_utc: datetime | None = None,
) -> list[int]:
    """Return every round already raced (event date on/before ``now_utc``).

    Pure function over a FastF1 schedule DataFrame — no network access — so the
    ingest task can backfill a whole season deterministically.

    Args:
        schedule: Schedule frame with ``EventDate``, ``RoundNumber`` and
            ``EventFormat`` columns (as returned by
            ``f1_predictions.utils.race_detector.get_event_schedule``).
        now_utc: Reference timestamp. Defaults to ``datetime.now(tz=UTC)``.

    Returns:
        Ascending list of completed round numbers. Empty if the schedule is
        empty or nothing has been raced yet.
    """
    if schedule is None or schedule.empty:
        return []

    reference = now_utc or datetime.now(tz=UTC)
    frame = pd.DataFrame(schedule).copy()
    frame["EventDate"] = pd.to_datetime(frame["EventDate"], utc=True)

    mask = (frame["EventDate"] <= pd.Timestamp(reference)) & (
        frame["EventFormat"] != "testing"
    )
    raced = frame.loc[mask, "RoundNumber"].dropna().astype(int)
    return sorted({int(r) for r in raced})


# ---------------------------------------------------------------------------
# Bronze transform
# ---------------------------------------------------------------------------


def _lap_time_seconds(series: pd.Series) -> pd.Series:
    """Coerce a lap-time column to float seconds.

    FastF1 emits ``LapTime`` as ``timedelta64``; the Bronze contract stores
    seconds so the DLT Silver cast is a no-op and SQL stays readable.

    Args:
        series: Raw lap-time values (timedelta, string, or numeric).

    Returns:
        Float64 Series of lap times in seconds (``NaN`` where unparseable).
    """
    if pd.api.types.is_timedelta64_dtype(series):
        return cast("pd.Series", series.dt.total_seconds().astype("float64"))
    if pd.api.types.is_numeric_dtype(series):
        return cast("pd.Series", series.astype("float64"))

    # FastF1 never emits datetimes as lap times, but an all-NaT column infers
    # ``datetime64``. Surface such values as missing instead of crashing —
    # the caller then drops the rows (and may report no valid laps).
    if pd.api.types.is_datetime64_any_dtype(series):
        return cast(
            "pd.Series", pd.Series([float("nan")] * len(series), index=series.index)
        )

    try:
        deltas = pd.to_timedelta(series)
    except (TypeError, ValueError):
        return cast(
            "pd.Series", pd.Series([float("nan")] * len(series), index=series.index)
        )
    return cast("pd.Series", deltas.dt.total_seconds().astype("float64"))


def build_bronze_laps(
    laps: pd.DataFrame,
    *,
    season: int,
    round_number: int,
    event_name: str,
    session_type: str = "Race",
) -> pd.DataFrame:
    """Reshape a FastF1 race-laps frame onto the Bronze column contract.

    Metadata (``Season``/``RoundNumber``/``SessionType``/``EventName``) is set
    authoritatively from the arguments rather than trusted from the source
    frame, so a mislabelled input can never poison the curated layers.

    Args:
        laps: FastF1 race laps DataFrame (must contain ``Driver``,
            ``LapNumber`` and ``LapTime``).
        season: F1 season year to stamp on every row.
        round_number: Round number to stamp on every row.
        event_name: Grand Prix name to stamp on every row.
        session_type: Session label; defaults to ``"Race"``.

    Returns:
        A new DataFrame with exactly :data:`BRONZE_LAP_COLUMNS`, sorted by
        driver and lap number.

    Raises:
        ValueError: If ``laps`` is empty.
        KeyError: If any required source column is missing.
        ValueError: If every row is dropped by cleaning (no valid laps).
    """
    if laps is None or laps.empty:
        msg = "Cannot build Bronze laps from an empty DataFrame."
        raise ValueError(msg)

    missing = [c for c in _REQUIRED_SOURCE_COLUMNS if c not in laps.columns]
    if missing:
        msg = f"Laps frame is missing required Bronze columns: {missing}"
        raise KeyError(msg)

    frame = pd.DataFrame(laps).copy()

    lap_time = _lap_time_seconds(frame["LapTime"])
    lap_number = pd.to_numeric(frame["LapNumber"], errors="coerce")

    if "TyreLife" in frame.columns:
        tyre_life = pd.to_numeric(frame["TyreLife"], errors="coerce")
    else:
        tyre_life = pd.Series([float("nan")] * len(frame), index=frame.index)

    if "Compound" in frame.columns:
        compound = frame["Compound"].astype("string")
    else:
        compound = pd.Series([pd.NA] * len(frame), index=frame.index, dtype="string")

    if "Stint" in frame.columns:
        stint = pd.to_numeric(frame["Stint"], errors="coerce").astype("Int64")
    else:
        stint = pd.Series([pd.NA] * len(frame), index=frame.index, dtype="Int64")

    if "Position" in frame.columns:
        position = pd.to_numeric(frame["Position"], errors="coerce").astype("Int64")
    else:
        position = pd.Series([pd.NA] * len(frame), index=frame.index, dtype="Int64")

    if "Team" in frame.columns:
        team = frame["Team"].astype("string")
    else:
        team = pd.Series([pd.NA] * len(frame), index=frame.index, dtype="string")

    driver = frame["Driver"].astype("string")

    # A row is only valid if the DLT expectations can pass: Driver must be
    # non-null (expect_or_fail) and the lap must have a number and a time.
    valid = driver.notna() & lap_number.notna() & lap_time.notna()

    out = pd.DataFrame(
        {
            "Driver": driver[valid],
            "LapNumber": lap_number[valid].astype("int64"),
            "LapTime": lap_time[valid].astype("float64"),
            "Compound": compound[valid],
            "TyreLife": tyre_life[valid].astype("float64"),
            "Stint": stint[valid],
            "Team": team[valid],
            "Position": position[valid],
            "SessionType": session_type,
            "EventName": event_name,
            "Season": int(season),
            "RoundNumber": int(round_number),
        }
    )

    if out.empty:
        msg = (
            f"No valid laps remained after cleaning for {season} R{round_number:02d}. "
            "FastF1 lap timing may be unavailable."
        )
        raise ValueError(msg)

    out = out.sort_values(["Driver", "LapNumber"], ignore_index=True)
    return out[list(BRONZE_LAP_COLUMNS)]
