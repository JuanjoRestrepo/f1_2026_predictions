"""Pandera schema definitions for FastF1 session DataFrames.

Rationale for schema-first design:
    Defining schemas as the first artifact of the ingestion module forces
    explicit contracts on what the pipeline accepts. Any upstream change in
    FastF1's output format (column renames, dtype shifts, new nullability)
    is caught at the ingestion boundary — not silently propagated into the
    cleaning or modeling stages where it would be much harder to diagnose.

    Pandera was chosen over Great Expectations for three reasons:
        1. Pandas-native API — schemas integrate directly with DataFrames.
        2. Lightweight — no server, no store, no YAML configuration files.
        3. Type-checkable via pandera.typing — mypy can verify Series types.

Schema versioning policy:
    When FastF1 changes its output format, bump the version constant below
    and add a migration note in CHANGELOG.md. Never silently update a schema.

Column selection rationale:
    Only columns consumed by the cleaning and feature engineering stages are
    declared. Telemetry channels (Car data, Position data) are loaded on
    demand by the telemetry sub-loader. Unknown extra columns pass through
    (strict=False) so new FastF1 releases do not break ingestion before we
    decide whether to incorporate the new columns.
"""

from typing import Optional

import pandas as pd
import pandera as pa
from pandera.typing import Series

LAPS_SCHEMA_VERSION: str = "1.0.0"
RESULTS_SCHEMA_VERSION: str = "1.0.0"


class LapsSchema(pa.DataFrameModel):
    """Schema for the FastF1 ``session.laps`` DataFrame.

    Covers both qualifying and race laps. Nullable flags reflect real-world
    F1 telemetry quality: out-laps, in-laps, red-flag periods, and DNF laps
    routinely produce null lap times and sector times.

    Attributes:
        Time: Timedelta from session start to end of this lap.
        LapTime: Total lap duration. Null for in/out-laps and aborted laps.
        LapNumber: Lap counter, 1-indexed per driver per session.
        Sector1Time: Sector 1 duration. Null for anomalous laps.
        Sector2Time: Sector 2 duration.
        Sector3Time: Sector 3 duration.
        PitOutTime: Pit-exit timestamp. Non-null only on out-laps.
        PitInTime: Pit-entry timestamp. Non-null only on in-laps.
        Driver: Three-letter FIA driver code (e.g. ``"VER"``).
        DriverNumber: FIA car number as string (e.g. ``"1"``).
        Team: Constructor name as returned by FastF1.
        Compound: Tyre compound. Null when tyre data is unavailable.
        TyreLife: Laps on current tyre set. Null when compound unknown.
        FreshTyre: Whether this is the first stint on this set.
        Stint: Stint index, 1-indexed per driver.
        SpeedI1: Speed trap at Intermediate 1 in km/h.
        SpeedI2: Speed trap at Intermediate 2 in km/h.
        SpeedFL: Speed at finish line in km/h.
        SpeedST: Speed at main speed trap in km/h.
        IsPersonalBest: Whether this lap is the driver's session best.
        TrackStatus: Single-char FIA track status code.
    """

    Time: Series[pd.Timedelta]
    LapTime: Optional[Series[pd.Timedelta]]       # type: ignore[type-arg]
    LapNumber: Series[pa.typing.Int64] = pa.Field(ge=1, le=100)
    Sector1Time: Optional[Series[pd.Timedelta]]   # type: ignore[type-arg]
    Sector2Time: Optional[Series[pd.Timedelta]]   # type: ignore[type-arg]
    Sector3Time: Optional[Series[pd.Timedelta]]   # type: ignore[type-arg]
    PitOutTime: Optional[Series[pd.Timestamp]] = pa.Field(nullable=True)  # type: ignore[type-arg]
    PitInTime: Optional[Series[pd.Timestamp]] = pa.Field(nullable=True)   # type: ignore[type-arg]

    Driver: Series[str] = pa.Field(str_length={"min_value": 2, "max_value": 3})
    DriverNumber: Series[str]
    Team: Series[str]

    Compound: Optional[Series[str]] = pa.Field(      # type: ignore[type-arg]
        nullable=True,
        isin=["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN"],
    )
    TyreLife: Optional[Series[pa.typing.Float64]]    # type: ignore[type-arg]
    FreshTyre: Optional[Series[bool]]                # type: ignore[type-arg]
    Stint: Optional[Series[pa.typing.Int64]] = pa.Field(nullable=True, ge=1)

    SpeedI1: Optional[Series[pa.typing.Float64]] = pa.Field(nullable=True, ge=0, le=450)  # type: ignore[type-arg]
    SpeedI2: Optional[Series[pa.typing.Float64]] = pa.Field(nullable=True, ge=0, le=450)  # type: ignore[type-arg]
    SpeedFL: Optional[Series[pa.typing.Float64]] = pa.Field(nullable=True, ge=0, le=450)  # type: ignore[type-arg]
    SpeedST: Optional[Series[pa.typing.Float64]] = pa.Field(nullable=True, ge=0, le=450)  # type: ignore[type-arg]

    IsPersonalBest: Optional[Series[bool]]           # type: ignore[type-arg]
    TrackStatus: Optional[Series[str]]               # type: ignore[type-arg]

    class Config:
        """Pandera DataFrameModel configuration."""

        # coerce=True auto-converts compatible dtypes (int32 → int64, etc.)
        # instead of raising on minor dtype differences between FastF1 versions.
        coerce = True
        # strict=False allows extra columns so new FastF1 releases that add
        # columns do not break the ingestion stage unexpectedly.
        strict = False


class ResultsSchema(pa.DataFrameModel):
    """Schema for the FastF1 ``session.results`` DataFrame.

    Covers the final classification table for qualifying and race sessions.
    Used to build the target variable (FinishPosition / total race time)
    and to join lap-level features to driver-level outcomes.

    Attributes:
        DriverNumber: FIA car number as string.
        BroadcastName: Driver name as broadcast (e.g. ``"M VERSTAPPEN"``).
        Abbreviation: Three-letter FIA driver code.
        TeamName: Constructor name.
        GridPosition: Starting grid position. Null for DNS/DQ entries.
        Position: Finishing position as float (DNF → NaN).
        Q1: Q1 best lap time. Non-null only in qualifying sessions.
        Q2: Q2 best lap time. Non-null if driver reached Q2.
        Q3: Q3 best lap time. Non-null if driver reached Q3.
        Time: Finishing time or gap to leader. Null for DNF.
        Status: Result status string (e.g. ``"Finished"``, ``"DNF"``).
        Points: Points awarded. Float to accommodate 0.5 fastest-lap bonus.
    """

    DriverNumber: Series[str]
    BroadcastName: Series[str]
    Abbreviation: Series[str] = pa.Field(str_length={"min_value": 2, "max_value": 3})
    TeamName: Series[str]
    GridPosition: Optional[Series[pa.typing.Float64]] = pa.Field(nullable=True, ge=0, le=25)   # type: ignore[type-arg]
    Position: Optional[Series[pa.typing.Float64]] = pa.Field(nullable=True, ge=1, le=25)       # type: ignore[type-arg]
    Q1: Optional[Series[pd.Timestamp]] = pa.Field(nullable=True)    # type: ignore[type-arg]
    Q2: Optional[Series[pd.Timestamp]] = pa.Field(nullable=True)    # type: ignore[type-arg]
    Q3: Optional[Series[pd.Timestamp]] = pa.Field(nullable=True)    # type: ignore[type-arg]
    Time: Optional[Series[pd.Timedelta]] = pa.Field(nullable=True)  # type: ignore[type-arg]
    Status: Series[str]
    Points: Optional[Series[pa.typing.Float64]] = pa.Field(nullable=True, ge=0, le=30)         # type: ignore[type-arg]

    class Config:
        """Pandera DataFrameModel configuration."""

        coerce = True
        strict = False
