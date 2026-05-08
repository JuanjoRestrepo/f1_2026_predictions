"""Session data extractors for qualifying and race sessions.

Responsibilities of this module:
    1. Extract the laps and results DataFrames from a loaded FastF1 session.
    2. Add pipeline metadata columns (``season``, ``round``, ``session_type``,
       ``event_name``) so every row is self-describing after Parquet writes.
    3. Validate the extracted DataFrames against their Pandera schemas before
       returning them — fail loudly at the boundary, not deep in the pipeline.
    4. Provide a unified ``load_qualifying()`` and ``load_race()`` interface
       so callers never interact with FastF1 internals directly.

Separation of concerns from ``fastf1_client.py``:
    ``fastf1_client.py``  → network layer: cache setup, retry, session loading.
    ``session_loader.py`` → data layer: extraction, enrichment, validation.
    ``parquet_writer.py`` → storage layer: serialisation and idempotent writes.

This separation ensures the data extraction logic is testable without a
network connection (mock the session object) and the client is testable
without touching the filesystem.
"""

from dataclasses import dataclass

import fastf1.core
import pandas as pd
import pandera.pandas as pa

from f1_predictions.ingestion.fastf1_client import SessionKey
from f1_predictions.ingestion.schemas import LapsSchema, ResultsSchema
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Metadata column names ─────────────────────────────────────────────────────
# Centralised here so column names are never duplicated across the codebase.
# The pipeline stages that consume these DataFrames should import these
# constants rather than hardcoding the strings.

COL_SEASON: str = "Season"
COL_ROUND: str = "RoundNumber"
COL_SESSION_TYPE: str = "SessionType"
COL_EVENT_NAME: str = "EventName"


# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QualifyingData:
    """Validated data extracted from a qualifying session.

    Attributes:
        key: The ``SessionKey`` identifying this session.
        laps: Validated laps DataFrame enriched with metadata columns.
        results: Validated results DataFrame with Q1/Q2/Q3 times.
    """

    key: SessionKey
    laps: pd.DataFrame
    results: pd.DataFrame


@dataclass(frozen=True)
class RaceData:
    """Validated data extracted from a race session.

    Attributes:
        key: The ``SessionKey`` identifying this session.
        laps: Validated laps DataFrame enriched with metadata columns.
        results: Validated results DataFrame with finishing positions.
        weather: Weather summary DataFrame (air temp, track temp, rainfall).
    """

    key: SessionKey
    laps: pd.DataFrame
    results: pd.DataFrame
    weather: pd.DataFrame


# ── Internal helpers ──────────────────────────────────────────────────────────


def _add_metadata_columns(df: pd.DataFrame, key: SessionKey) -> pd.DataFrame:
    """Append pipeline metadata columns to a DataFrame.

    Every row in the pipeline output must be self-describing so that
    Parquet files can be filtered by season, round, or session type
    without relying on file path conventions.

    The metadata columns are inserted at position 0-3 so they appear
    first in exploratory previews (``df.head()``).

    Args:
        df: The source DataFrame to enrich. Not mutated — a copy is returned.
        key: The ``SessionKey`` for the current session.

    Returns:
        A new DataFrame with four metadata columns prepended.
    """
    enriched = df.copy()
    enriched.insert(0, COL_EVENT_NAME, key.event_name)
    enriched.insert(0, COL_SESSION_TYPE, key.identifier)
    enriched.insert(0, COL_ROUND, key.round_number)
    enriched.insert(0, COL_SEASON, key.year)
    return enriched


def _validate_laps(df: pd.DataFrame, key: SessionKey) -> pd.DataFrame:
    """Validate a laps DataFrame against LapsSchema.

    Pandera raises ``SchemaError`` if a column fails its constraint.
    The error is logged with full context before re-raising so the
    pipeline log captures exactly which session and column failed.

    Args:
        df: The enriched laps DataFrame to validate.
        key: Session key for log context.

    Returns:
        The validated DataFrame (same object, Pandera validates in-place
        when ``inplace=True``; here we validate and return the input).

    Raises:
        pa.errors.SchemaError: If any column violates its schema contract.
    """
    try:
        LapsSchema.validate(df, lazy=True)
        logger.debug("LapsSchema validation passed for session: %s", key)
    except pa.errors.SchemaErrors as exc:
        logger.exception(
            "LapsSchema validation FAILED for session %s - %d error(s):\n%s",
            key,
            len(exc.failure_cases),
            exc.failure_cases.to_string(),
        )
        raise
    return df


def _validate_results(df: pd.DataFrame, key: SessionKey) -> pd.DataFrame:
    """Validate a results DataFrame against ResultsSchema.

    Args:
        df: The enriched results DataFrame to validate.
        key: Session key for log context.

    Returns:
        The validated DataFrame.

    Raises:
        pa.errors.SchemaErrors: If any column violates its schema contract.
    """
    try:
        ResultsSchema.validate(df, lazy=True)
        logger.debug("ResultsSchema validation passed for session: %s", key)
    except pa.errors.SchemaErrors as exc:
        logger.exception(
            "ResultsSchema validation FAILED for session %s - %d error(s):\n%s",
            key,
            len(exc.failure_cases),
            exc.failure_cases.to_string(),
        )
        raise
    return df


def _extract_weather_timeseries(session: fastf1.core.Session) -> pd.DataFrame:
    """Extract full weather timeseries from a loaded session.

    FastF1's ``session.weather_data`` returns samples throughout the session.
    We return the full DataFrame so it can be joined with laps using timestamps.

    Args:
        session: A loaded FastF1 session.

    Returns:
        DataFrame with the full weather timeseries.
    """
    try:
        w = session.weather_data
        if w is None or w.empty:
            logger.warning("No weather data available for session.")
            return pd.DataFrame()

        # Cast to plain DataFrame and ensure 'Time' column is clean
        df_weather = pd.DataFrame(w).copy()
        logger.debug("Weather timeseries extracted: %d samples", len(df_weather))
    except (KeyError, AttributeError) as exc:
        logger.warning(
            "Weather extraction failed (%s: %s). Returning empty DataFrame.",
            type(exc).__name__,
            exc,
        )
        return pd.DataFrame()
    else:
        return df_weather


# ── Public API ────────────────────────────────────────────────────────────────


def load_qualifying(
    session: fastf1.core.Session,
    key: SessionKey,
) -> QualifyingData:
    """Extract, enrich, and validate qualifying session data.

    Processes ``session.laps`` and ``session.results`` into validated
    DataFrames ready for the cleaning stage. Metadata columns are
    prepended so each row is self-describing in storage.

    Args:
        session: A loaded FastF1 session. Must have been loaded with
            ``laps=True`` (enforced by ``fastf1_client.load_session()``).
        key: The ``SessionKey`` for this session (year, round, identifier,
            event name). Produced by ``fastf1_client.load_session()``.

    Returns:
        A ``QualifyingData`` dataclass with validated ``laps`` and
        ``results`` DataFrames.

    Raises:
        fastf1.core.DataNotLoadedError: If ``session.load()`` was not called.
        pa.errors.SchemaErrors: If extracted data violates the schema.

    Example::

        from f1_predictions.ingestion.fastf1_client import load_session
        from f1_predictions.ingestion.session_loader import load_qualifying

        session, key = load_session(2025, 1, "Q")
        quali_data = load_qualifying(session, key)
        print(quali_data.laps.shape)
        print(quali_data.results[["Abbreviation", "Q1", "Q3"]].head())
    """
    logger.info("Extracting qualifying data: %s", key)

    # Cast FastF1.Laps/Results (pd.DataFrame subclasses) to plain DataFrame.
    # Pandera's backend resolver does not recognise subclass types and raises
    # BackendNotFoundError. pd.DataFrame() constructor preserves all columns/dtypes.
    raw_laps: pd.DataFrame = pd.DataFrame(session.laps)
    raw_results: pd.DataFrame = pd.DataFrame(session.results)

    logger.debug(
        "Raw laps shape: %s | Raw results shape: %s",
        raw_laps.shape,
        raw_results.shape,
    )

    laps = _add_metadata_columns(raw_laps, key)
    results = _add_metadata_columns(raw_results, key)

    laps = _validate_laps(laps, key)
    results = _validate_results(results, key)

    logger.info(
        "Qualifying extraction complete: %s | laps=%d  drivers=%d",
        key,
        len(laps),
        len(results),
    )
    return QualifyingData(key=key, laps=laps, results=results)


def load_race(
    session: fastf1.core.Session,
    key: SessionKey,
) -> RaceData:
    """Extract, enrich, and validate race session data.

    Processes ``session.laps``, ``session.results``, and weather data
    into validated DataFrames ready for the cleaning stage.

    Args:
        session: A loaded FastF1 session with laps and weather loaded.
        key: The ``SessionKey`` for this session.

    Returns:
        A ``RaceData`` dataclass with validated ``laps``, ``results``,
        and ``weather`` DataFrames.

    Raises:
        fastf1.core.DataNotLoadedError: If ``session.load()`` was not called.
        pa.errors.SchemaErrors: If extracted data violates the schema.

    Example::

        from f1_predictions.ingestion.fastf1_client import load_session
        from f1_predictions.ingestion.session_loader import load_race

        session, key = load_session(2025, 1, "R")
        race_data = load_race(session, key)
        print(race_data.results[["Abbreviation", "Position", "Status"]].head(10))
    """
    logger.info("Extracting race data: %s", key)

    # Same cast as load_qualifying — Pandera requires plain pd.DataFrame.
    raw_laps: pd.DataFrame = pd.DataFrame(session.laps)
    raw_results: pd.DataFrame = pd.DataFrame(session.results)

    logger.debug(
        "Raw laps shape: %s | Raw results shape: %s",
        raw_laps.shape,
        raw_results.shape,
    )

    laps = _add_metadata_columns(raw_laps, key)
    results = _add_metadata_columns(raw_results, key)
    weather = _extract_weather_timeseries(session)

    laps = _validate_laps(laps, key)
    results = _validate_results(results, key)

    logger.info(
        "Race extraction complete: %s | laps=%d  drivers=%d  rainfall=%s",
        key,
        len(laps),
        len(results),
        weather.get("Rainfall_any", [None])[0] if not weather.empty else "N/A",
    )
    return RaceData(key=key, laps=laps, results=results, weather=weather)
