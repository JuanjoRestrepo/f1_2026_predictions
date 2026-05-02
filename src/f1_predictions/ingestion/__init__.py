"""Ingestion package for the f1_predictions pipeline.

Public API:

Network / session loading::

    load_session          : Load a FastF1 session with retry logic.
    SessionKey            : Immutable session identifier.
    SessionIdentifier     : Literal type for valid session codes.

Data extraction::

    load_qualifying       : Extract and validate qualifying laps + results.
    load_race             : Extract and validate race laps + results + weather.
    QualifyingData        : Frozen dataclass returned by load_qualifying().
    RaceData              : Frozen dataclass returned by load_race().

Storage::

    write_parquet         : Write a DataFrame to a partitioned Parquet file.
    read_parquet          : Read a session Parquet file back to a DataFrame.
    resolve_parquet_path  : Compute the canonical path without writing.
    DataType              : Enum of writable data types (LAPS, RESULTS, WEATHER).

Schemas::

    LapsSchema            : Pandera schema for session.laps DataFrames.
    ResultsSchema         : Pandera schema for session.results DataFrames.

Metadata column name constants::

    COL_SEASON            : "Season"
    COL_ROUND             : "RoundNumber"
    COL_SESSION_TYPE      : "SessionType"
    COL_EVENT_NAME        : "EventName"
"""

from f1_predictions.ingestion.fastf1_client import (
    SessionIdentifier,
    SessionKey,
    load_session,
)
from f1_predictions.ingestion.parquet_writer import (
    DataType,
    read_parquet,
    resolve_parquet_path,
    write_parquet,
)
from f1_predictions.ingestion.schemas import LapsSchema, ResultsSchema
from f1_predictions.ingestion.session_loader import (
    COL_EVENT_NAME,
    COL_ROUND,
    COL_SEASON,
    COL_SESSION_TYPE,
    QualifyingData,
    RaceData,
    load_qualifying,
    load_race,
)

__all__ = [
    # Client
    "load_session",
    "SessionKey",
    "SessionIdentifier",
    # Loaders
    "load_qualifying",
    "load_race",
    "QualifyingData",
    "RaceData",
    # Storage
    "write_parquet",
    "read_parquet",
    "resolve_parquet_path",
    "DataType",
    # Schemas
    "LapsSchema",
    "ResultsSchema",
    # Constants
    "COL_SEASON",
    "COL_ROUND",
    "COL_SESSION_TYPE",
    "COL_EVENT_NAME",
]
