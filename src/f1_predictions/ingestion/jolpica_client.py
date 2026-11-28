"""Jolpica F1 API client for championship standings data.

Jolpica (https://jolpica.com) is the maintained drop-in replacement for the
deprecated Ergast F1 API, exposing the same JSON schema at:
``https://api.jolpica.com/ergast/v1/f1/``

No authentication is required.  The API is free and returns cumulative
championship standings as of a specific round, making it ideal for the
``championship_standings_round_N.json`` artifact that powers the
``ChampionshipProgression`` dashboard component.

Both driver and constructor standings are fetched per round and assembled
into a single combined artifact.

Output JSON schema (``championship_standings_round_N.json``)::

    {
      "event": str,
      "year": int,
      "round": int,
      "drivers": [
        {"position": int, "driver": str, "team": str, "color": str, "points": float}
      ],
      "constructors": [
        {"position": int, "team": str, "color": str, "points": float}
      ]
    }
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from f1_predictions.utils.logging_setup import get_logger

logger: logging.Logger = get_logger(__name__)

_BASE_URL = "https://api.jolpica.com/ergast/v1/f1"
_TIMEOUT = 15.0  # seconds

# Team-name aliases: Jolpica uses 2024-era names; map to our 2026 palette.
_TEAM_NAME_MAP: dict[str, str] = {
    "Red Bull": "Red Bull Racing",
    "RB F1 Team": "Racing Bulls",
    "Visa Cash App RB F1 Team": "Racing Bulls",
    "Stake F1 Team Kick Sauber": "Sauber",
    "MoneyGram Haas F1 Team": "Haas",
    "Alpine F1 Team": "Alpine",
    "Aston Martin Aramco F1 Team": "Aston Martin",
    "Williams Racing": "Williams",
    "BWT Alpine F1 Team": "Alpine",
}

_TEAM_COLORS: dict[str, str] = {
    "Mercedes": "#27F4D2",
    "Red Bull Racing": "#3671C6",
    "Ferrari": "#E8002D",
    "McLaren": "#FF8000",
    "Aston Martin": "#229971",
    "Alpine": "#0093CC",
    "Williams": "#64C4FF",
    "Racing Bulls": "#6692FF",
    "Sauber": "#52E252",
    "Kick Sauber": "#52E252",
    "Haas": "#B6BABD",
    "Haas F1 Team": "#B6BABD",
    "Audi": "#f50531",
    "Cadillac": "#FFD700",
}

_DEFAULT_COLOR = "#888888"

# Map Jolpica driver codes (which may differ from FastF1 3-letter codes) to
# our canonical abbreviations.  Extends as new drivers join.
_DRIVER_CODE_MAP: dict[str, str] = {
    "antonelli": "ANT",
    "hadjar": "HAD",
    "bearman": "BEA",
    "bortoleto": "BOR",
    "colapinto": "COL",
    "doohan": "DOO",
    "lindblad": "LIN",
}


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _get_json(url: str) -> dict[str, Any]:
    """Execute a GET request and return the parsed JSON body.

    Args:
        url: Fully qualified URL.

    Returns:
        Parsed JSON body as a dict.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses (after retries).
        httpx.RequestError: On network-level errors (after retries).
    """
    logger.debug("Jolpica GET %s", url)
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    return data


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------


def fetch_driver_standings(year: int, round_number: int) -> list[dict[str, Any]]:
    """Fetch driver championship standings after a specific round.

    Args:
        year: Championship season, e.g. ``2026``.
        round_number: Round number within the season (1-indexed).

    Returns:
        List of ``StandingsLists[0].DriverStandings`` dicts from the
        Jolpica/Ergast API, sorted by position.  Returns an empty list on
        any error.
    """
    url = f"{_BASE_URL}/{year}/{round_number}/driverStandings.json"
    logger.info("Jolpica: fetching driver standings %d R%02d", year, round_number)
    try:
        data = _get_json(url)
        standings_lists = (
            data.get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        if not standings_lists:
            logger.warning(
                "Jolpica: empty StandingsLists for %d R%02d", year, round_number
            )
            return []
        rows: list[dict[str, Any]] = standings_lists[0].get("DriverStandings", [])
        logger.info("Jolpica: got %d driver standings rows", len(rows))
    except Exception as exc:
        logger.warning("Jolpica driver standings fetch failed: %s", exc)
        return []
    else:
        return rows


def fetch_constructor_standings(year: int, round_number: int) -> list[dict[str, Any]]:
    """Fetch constructor championship standings after a specific round.

    Args:
        year: Championship season, e.g. ``2026``.
        round_number: Round number within the season (1-indexed).

    Returns:
        List of ``StandingsLists[0].ConstructorStandings`` dicts from the
        Jolpica/Ergast API, sorted by position.  Returns an empty list on
        any error.
    """
    url = f"{_BASE_URL}/{year}/{round_number}/constructorStandings.json"
    logger.info("Jolpica: fetching constructor standings %d R%02d", year, round_number)
    try:
        data = _get_json(url)
        standings_lists = (
            data.get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        if not standings_lists:
            logger.warning(
                "Jolpica: empty constructor StandingsLists for %d R%02d",
                year,
                round_number,
            )
            return []
        rows: list[dict[str, Any]] = standings_lists[0].get("ConstructorStandings", [])
        logger.info("Jolpica: got %d constructor standings rows", len(rows))
    except Exception as exc:
        logger.warning("Jolpica constructor standings fetch failed: %s", exc)
        return []
    else:
        return rows


# ---------------------------------------------------------------------------
# Artifact builder
# ---------------------------------------------------------------------------


def _normalize_team(raw_name: str) -> str:
    """Normalise a Jolpica constructor name to our 2026 palette key.

    Args:
        raw_name: Constructor name as returned by Jolpica.

    Returns:
        Canonical team name string.
    """
    return _TEAM_NAME_MAP.get(raw_name, raw_name)


def _normalize_driver(code: str, family_name: str) -> str:
    """Return the canonical 3-letter driver abbreviation.

    Jolpica exposes a ``code`` field (e.g. ``"VER"``) which matches our
    system for established drivers.  Rookie drivers may use their ``driverId``
    slug instead — handle via ``_DRIVER_CODE_MAP``.

    Args:
        code: Jolpica ``Driver.code`` field (may be empty for new drivers).
        family_name: Driver family name used as final fallback.

    Returns:
        Three-letter abbreviation string.
    """
    if code and len(code) == 3:
        return code.upper()
    slug_key = family_name.lower()
    return _DRIVER_CODE_MAP.get(slug_key, family_name[:3].upper())


def build_championship_standings(
    driver_standings: list[dict[str, Any]],
    constructor_standings: list[dict[str, Any]],
    event_name: str,
    year: int,
    round_number: int,
) -> dict[str, Any]:
    """Assemble the championship-standings artifact from Jolpica raw data.

    Args:
        driver_standings: Rows from :func:`fetch_driver_standings`.
        constructor_standings: Rows from :func:`fetch_constructor_standings`.
        event_name: Human-readable event name, e.g. ``"Qatar Grand Prix"``.
        year: Championship season.
        round_number: Round number this snapshot covers.

    Returns:
        Dictionary matching the ``championship_standings_round_N.json`` schema.
    """
    drivers_out: list[dict[str, Any]] = []
    for row in driver_standings:
        driver_info = row.get("Driver", {})
        constructor_list = row.get("Constructors", [{}])
        constructor_name = (
            constructor_list[0].get("name", "Unknown")
            if constructor_list
            else "Unknown"
        )
        team = _normalize_team(constructor_name)

        code = driver_info.get("code", "")
        family_name = driver_info.get("familyName", "UNK")
        abbr = _normalize_driver(code, family_name)

        try:
            pos = int(row.get("position", 0))
        except (ValueError, TypeError):
            pos = 0

        try:
            pts = float(row.get("points", 0))
        except (ValueError, TypeError):
            pts = 0.0

        drivers_out.append(
            {
                "position": pos,
                "driver": abbr,
                "team": team,
                "color": _TEAM_COLORS.get(team, _DEFAULT_COLOR),
                "points": pts,
            }
        )

    constructors_out: list[dict[str, Any]] = []
    for row in constructor_standings:
        constructor_info = row.get("Constructor", {})
        raw_name = constructor_info.get("name", "Unknown")
        team = _normalize_team(raw_name)

        try:
            pos = int(row.get("position", 0))
        except (ValueError, TypeError):
            pos = 0

        try:
            pts = float(row.get("points", 0))
        except (ValueError, TypeError):
            pts = 0.0

        constructors_out.append(
            {
                "position": pos,
                "team": team,
                "color": _TEAM_COLORS.get(team, _DEFAULT_COLOR),
                "points": pts,
            }
        )

    logger.info(
        "build_championship_standings: %d drivers, %d constructors",
        len(drivers_out),
        len(constructors_out),
    )

    return {
        "event": event_name,
        "year": year,
        "round": round_number,
        "drivers": drivers_out,
        "constructors": constructors_out,
    }
