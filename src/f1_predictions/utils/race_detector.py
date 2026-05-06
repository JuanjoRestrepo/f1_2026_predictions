"""Race weekend auto-detector for the F1 2026 prediction pipeline.

Rationale for this module:
    - Acts as the "smart gate" before the full pipeline runs.
    - Prevents unnecessary FastF1 downloads and ML computation on non-race weeks.
    - Uses only fastf1.get_event_schedule() (lightweight metadata fetch, no
      telemetry download) to determine if a race completed in the last N days.
    - Design: pure functions with no side effects — fully testable without
      mocking FastF1 network calls (just inject a prebuilt DataFrame).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import fastf1
import pandas as pd

logger = logging.getLogger(__name__)

# Races older than this threshold are considered "stale" and skipped.
# Set to 2 to cover Monday + Tuesday UTC edge cases.
_DEFAULT_DAYS_BACK: int = 2

# FastF1 event type identifier for a full race weekend.
_RACE_EVENT_TYPE: str = "Race"


def get_event_schedule(season: int) -> pd.DataFrame:
    """Fetch the full event schedule for a given F1 season.

    Isolated for testability — callers can mock this function to inject
    a prebuilt schedule DataFrame without hitting the FastF1 network.

    Args:
        season: The F1 season year (e.g. 2026).

    Returns:
        DataFrame with columns including 'EventDate', 'EventName',
        'RoundNumber', and 'EventFormat'.
    """
    logger.debug("Fetching FastF1 event schedule for season %d", season)
    schedule: pd.DataFrame = fastf1.get_event_schedule(season, include_testing=False)
    return schedule


def find_last_completed_race(
    schedule: pd.DataFrame,
    now_utc: datetime | None = None,
    days_back: int = _DEFAULT_DAYS_BACK,
) -> dict[str, Any] | None:
    """Determine if a race was completed within the last N days.

    Compares each race event's date against the current UTC time. Returns
    the most recently completed event metadata if found, otherwise None.

    This function is pure — it takes the schedule as input rather than
    fetching it, making it trivially testable without network access.

    Args:
        schedule: FastF1 event schedule DataFrame from `get_event_schedule`.
        now_utc: The reference timestamp. Defaults to `datetime.utcnow()`.
            Inject a fixed datetime in tests for deterministic behaviour.
        days_back: Number of days to look back from `now_utc`. Default 2.

    Returns:
        A dict with keys 'round', 'gp_name', 'event_date' if a race is
        found within the window, or None if no race occurred.
    """
    if now_utc is None:
        now_utc = datetime.now(tz=UTC)

    if schedule.empty:
        logger.info("Event schedule is empty, no race to detect.")
        return None

    # Normalize schedule dates to UTC-aware timestamps for comparison.
    # FastF1 returns timezone-naive dates; we assume UTC convention.
    schedule = schedule.copy()
    schedule["EventDate"] = pd.to_datetime(schedule["EventDate"], utc=True)

    # Filter to completed race events within the lookback window.
    cutoff = now_utc - pd.Timedelta(days=days_back)
    mask = (
        (schedule["EventDate"] >= cutoff)
        & (schedule["EventDate"] <= now_utc)
        & (schedule["EventFormat"] != "testing")
    )
    recent = schedule.loc[mask]

    if recent.empty:
        logger.info(
            "No race found in the last %d day(s) (now=%s).",
            days_back,
            now_utc.isoformat(),
        )
        return None

    # Take the most recent event if multiple fall in the window (edge case).
    latest = recent.sort_values("EventDate").iloc[-1]
    result: dict[str, Any] = {
        "round": int(latest["RoundNumber"]),
        "gp_name": str(latest["EventName"]),
        "event_date": latest["EventDate"].isoformat(),
    }
    logger.info(
        "Race detected: Round %d — %s (%s)",
        result["round"],
        result["gp_name"],
        result["event_date"],
    )
    return result


def find_upcoming_race(
    schedule: pd.DataFrame,
    now_utc: datetime | None = None,
    days_ahead: int = 3,
) -> dict[str, Any] | None:
    """Determine if a race is scheduled within the next N days.

    Args:
        schedule: FastF1 event schedule DataFrame.
        now_utc: Reference timestamp.
        days_ahead: Lookahead window in days. Default 3.

    Returns:
        Race metadata dict if found, otherwise None.
    """
    if now_utc is None:
        now_utc = datetime.now(tz=UTC)

    if schedule.empty:
        return None

    schedule = schedule.copy()
    schedule["EventDate"] = pd.to_datetime(schedule["EventDate"], utc=True)

    # Filter to future race events within the lookahead window.
    cutoff = now_utc + pd.Timedelta(days=days_ahead)
    mask = (
        (schedule["EventDate"] > now_utc)
        & (schedule["EventDate"] <= cutoff)
        & (schedule["EventFormat"] != "testing")
    )
    upcoming = schedule.loc[mask]

    if upcoming.empty:
        logger.info("No upcoming race found in the next %d days.", days_ahead)
        return None

    # Take the next occurring event.
    next_gp = upcoming.sort_values("EventDate").iloc[0]
    return {
        "round": int(next_gp["RoundNumber"]),
        "gp_name": str(next_gp["EventName"]),
        "event_date": next_gp["EventDate"].isoformat(),
    }


def detect_last_race(
    season: int,
    days_back: int = _DEFAULT_DAYS_BACK,
    now_utc: datetime | None = None,
) -> dict[str, Any] | None:
    """High-level entry point: fetch schedule and detect the last race.

    Combines `get_event_schedule` and `find_last_completed_race` into
    a single convenience function for use in CI scripts and workflows.

    Args:
        season: F1 season year.
        days_back: Lookback window in days.
        now_utc: Override for the current UTC time (for testing).

    Returns:
        Race metadata dict or None if no race in the window.
    """
    schedule = get_event_schedule(season)
    return find_last_completed_race(schedule, now_utc=now_utc, days_back=days_back)


def detect_upcoming_race(
    season: int,
    days_ahead: int = 3,
    now_utc: datetime | None = None,
) -> dict[str, Any] | None:
    """High-level entry point: detect the next scheduled race.

    Args:
        season: F1 season year.
        days_ahead: Lookahead window in days.
        now_utc: Override for testing.

    Returns:
        Upcoming race metadata or None.
    """
    schedule = get_event_schedule(season)
    return find_upcoming_race(schedule, now_utc=now_utc, days_ahead=days_ahead)
