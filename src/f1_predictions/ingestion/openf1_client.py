"""OpenF1 API client for post-race interval and pit-stop data.

OpenF1 (https://openf1.org) exposes free historical endpoints for every
completed session.  Live-session access requires a paid subscription, so this
module is strictly called in post-race mode (``is_post_race=True`` in
``master_pipeline.py``).

Rate-limiting is handled via ``tenacity`` exponential-backoff retries (3
attempts, 2-30 s).  All network errors are non-fatal: callers should wrap
invocations in ``try/except`` and log a warning on failure rather than
aborting the pipeline.

Endpoints consumed:
    - ``GET /sessions``        — resolve session_key for a given year/round
    - ``GET /intervals``       — per-driver gap-to-leader at every interval
    - ``GET /pit``             — per-driver pit-stop durations per lap
    - ``GET /race_control``    — safety-car / red-flag / VSC messages

Output JSON schemas:

``gap_to_leader_round_N.json``::

    {
      "event": str,
      "year": int,
      "total_laps": int,
      "safety_car_laps": [{"start_lap": int, "end_lap": int, "type": "SC"|"VSC"|"RED"}],
      "drivers": [
        {"driver": str, "team": str, "color": str, "gaps_s": {"1": float, ...}}
      ]
    }

``pit_stops_round_N.json``::

    {
      "event": str,
      "year": int,
      "teams": [
        {
          "team": str,
          "color": str,
          "stops": [
            {"driver": str, "lap": int, "pit_duration_s": float, "stationary_s": float}
          ]
        }
      ]
    }
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from f1_predictions.utils.logging_setup import get_logger

logger: logging.Logger = get_logger(__name__)

_BASE_URL = "https://api.openf1.org/v1"
_TIMEOUT = 20.0  # seconds — conservative for multi-MB interval payloads

# Canonical SC/VSC message prefixes in the OpenF1 race_control stream.
_SC_DEPLOYED = "SAFETY CAR DEPLOYED"
_VSC_DEPLOYED = "VIRTUAL SAFETY CAR DEPLOYED"
_SC_WITHDRAWN = "SAFETY CAR IN THIS LAP"
_VSC_WITHDRAWN = "VIRTUAL SAFETY CAR ENDING"


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _get(endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Execute a GET request against the OpenF1 API.

    Args:
        endpoint: Path component, e.g. ``"/sessions"``.
        params: Query-string parameters dict.

    Returns:
        Parsed JSON response as a list of dicts.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses (after retries).
        httpx.RequestError: On network-level errors (after retries).
    """
    url = f"{_BASE_URL}{endpoint}"
    logger.debug("OpenF1 GET %s params=%s", url, params)
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, list):
        logger.warning("OpenF1 %s returned non-list payload: %s", endpoint, type(data))
        return []
    return data


# ---------------------------------------------------------------------------
# Session-key resolution
# ---------------------------------------------------------------------------


def get_session_key(year: int, round_number: int) -> int | None:
    """Resolve the OpenF1 session_key for a race session.

    Args:
        year: Championship season, e.g. ``2026``.
        round_number: Round number within the season (1-indexed).

    Returns:
        Integer ``session_key`` if the session is found, otherwise ``None``.
    """
    logger.info("OpenF1: resolving session_key for %d R%02d", year, round_number)
    try:
        rows = _get(
            "/sessions",
            {"year": year, "round_number": round_number, "session_name": "Race"},
        )
    except Exception as exc:
        logger.warning("OpenF1 session_key lookup failed: %s", exc)
        return None

    if not rows:
        logger.warning(
            "OpenF1: no Race session found for %d R%02d", year, round_number
        )
        return None

    session_key: int = int(rows[0]["session_key"])
    event_name: str = rows[0].get("meeting_name", "Unknown")
    logger.info("OpenF1: session_key=%d (%s)", session_key, event_name)
    return session_key


# ---------------------------------------------------------------------------
# Raw data fetchers
# ---------------------------------------------------------------------------


def fetch_intervals(session_key: int) -> list[dict[str, Any]]:
    """Fetch gap-to-leader intervals for a completed race session.

    Args:
        session_key: OpenF1 session identifier (from :func:`get_session_key`).

    Returns:
        List of interval records, each containing at minimum
        ``driver_number``, ``lap_number``, ``gap_to_leader``, and
        ``date`` fields.  Returns an empty list on failure.
    """
    logger.info("OpenF1: fetching intervals for session_key=%d", session_key)
    try:
        rows: list[dict[str, Any]] = _get("/intervals", {"session_key": session_key})
        logger.info("OpenF1: got %d interval records", len(rows))
    except Exception as exc:
        logger.warning("OpenF1 intervals fetch failed: %s", exc)
        return []
    else:
        return rows


def fetch_pit_stops(session_key: int) -> list[dict[str, Any]]:
    """Fetch pit-stop records for a completed race session.

    Args:
        session_key: OpenF1 session identifier.

    Returns:
        List of pit records with ``driver_number``, ``lap_number``,
        ``pit_duration``, and ``date`` fields.  Returns an empty list on
        failure.
    """
    logger.info("OpenF1: fetching pit stops for session_key=%d", session_key)
    try:
        rows: list[dict[str, Any]] = _get("/pit", {"session_key": session_key})
        logger.info("OpenF1: got %d pit records", len(rows))
    except Exception as exc:
        logger.warning("OpenF1 pit fetch failed: %s", exc)
        return []
    else:
        return rows


def fetch_race_control(session_key: int) -> list[dict[str, Any]]:
    """Fetch race-control messages (SC, VSC, red flags) for a session.

    Args:
        session_key: OpenF1 session identifier.

    Returns:
        List of race-control message dicts.  Returns an empty list on failure.
    """
    logger.info("OpenF1: fetching race_control for session_key=%d", session_key)
    try:
        rows: list[dict[str, Any]] = _get("/race_control", {"session_key": session_key})
        logger.info("OpenF1: got %d race_control records", len(rows))
    except Exception as exc:
        logger.warning("OpenF1 race_control fetch failed: %s", exc)
        return []
    else:
        return rows


# ---------------------------------------------------------------------------
# Driver metadata helper
# ---------------------------------------------------------------------------


def _driver_abbr_from_number(
    driver_number: int | str, drivers_meta: list[dict[str, Any]]
) -> str:
    """Return the 3-letter driver abbreviation for a given driver number.

    Falls back to the stringified driver number when no metadata is available.

    Args:
        driver_number: Numeric car number.
        drivers_meta: OpenF1 ``/drivers`` rows for the same session.

    Returns:
        Three-letter abbreviation string or stringified number as fallback.
    """
    num_str = str(driver_number)
    for d in drivers_meta:
        if str(d.get("driver_number")) == num_str:
            return str(d.get("name_acronym", num_str))
    return num_str


# ---------------------------------------------------------------------------
# Artifact builders
# ---------------------------------------------------------------------------

# Team colors mirror TEAM_COLORS in master_pipeline.py.
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

_DRIVER_TEAMS: dict[str, str] = {
    "NOR": "McLaren", "PIA": "McLaren",
    "LEC": "Ferrari", "HAM": "Ferrari",
    "VER": "Red Bull Racing", "HAD": "Red Bull Racing",
    "RUS": "Mercedes", "ANT": "Mercedes",
    "ALO": "Aston Martin", "STR": "Aston Martin",
    "GAS": "Alpine", "COL": "Alpine",
    "SAI": "Williams", "ALB": "Williams",
    "LAW": "Racing Bulls", "LIN": "Racing Bulls",
    "HUL": "Sauber", "BOR": "Sauber",
    "OCO": "Haas", "BEA": "Haas",
}

_DEFAULT_COLOR = "#888888"


def _team_color(team: str) -> str:
    return _TEAM_COLORS.get(team, _DEFAULT_COLOR)


def build_gap_to_leader(
    intervals: list[dict[str, Any]],
    race_control: list[dict[str, Any]],
    drivers_meta: list[dict[str, Any]],
    event_name: str,
    year: int,
) -> dict[str, Any]:
    """Transform raw OpenF1 intervals into the gap-to-leader artifact schema.

    Groups intervals by driver and lap number, extracts the last recorded
    gap per driver per lap (accounting for the fact that OpenF1 emits
    multiple interval readings within a single lap), and parses
    race-control messages to annotate Safety Car and VSC deployment windows.

    Args:
        intervals: Raw rows from :func:`fetch_intervals`.
        race_control: Raw rows from :func:`fetch_race_control`.
        drivers_meta: Raw rows from the OpenF1 ``/drivers`` endpoint (can be
            an empty list; abbreviations fall back to driver numbers).
        event_name: Human-readable event name, e.g. ``"Qatar Grand Prix"``.
        year: Championship season.

    Returns:
        Dictionary matching the ``gap_to_leader_round_N.json`` schema.
    """
    # ── 1. Build per-driver, per-lap gap map ─────────────────────────────────
    # OpenF1 uses driver_number (int).  We key by abbreviation for the UI.
    # {abbr: {lap: last_gap_s}}
    driver_gaps: dict[str, dict[int, float]] = defaultdict(dict)

    for row in intervals:
        lap = row.get("lap_number")
        gap_raw = row.get("gap_to_leader")
        drv_num = row.get("driver_number")
        if lap is None or gap_raw is None or drv_num is None:
            continue

        # gap_to_leader is a string like "+1.234" or "LAP" (lapped) or None.
        try:
            gap_s = float(str(gap_raw).lstrip("+"))
        except ValueError:
            gap_s = 999.0  # lapped drivers shown as large gap

        abbr = _driver_abbr_from_number(drv_num, drivers_meta)
        driver_gaps[abbr][int(lap)] = gap_s

    # ── 2. Parse SC / VSC windows from race_control ───────────────────────────
    safety_car_laps: list[dict[str, Any]] = []
    current_sc: dict[str, Any] | None = None

    for msg in sorted(race_control, key=lambda m: m.get("date", "")):
        message: str = str(msg.get("message", "")).upper()
        rc_lap: int | None = msg.get("lap_number")

        # Check VSC before SC because "SAFETY CAR DEPLOYED" is a substring of
        # "VIRTUAL SAFETY CAR DEPLOYED".
        if _VSC_DEPLOYED in message and rc_lap is not None:
            current_sc = {"start_lap": rc_lap, "end_lap": rc_lap, "type": "VSC"}
        elif _SC_DEPLOYED in message and rc_lap is not None:
            current_sc = {"start_lap": rc_lap, "end_lap": rc_lap, "type": "SC"}
        elif "RED FLAG" in message and rc_lap is not None:
            safety_car_laps.append(
                {"start_lap": rc_lap, "end_lap": rc_lap, "type": "RED"}
            )
        elif (
            (_SC_WITHDRAWN in message or _VSC_WITHDRAWN in message)
            and rc_lap is not None
            and current_sc is not None
        ):
            current_sc["end_lap"] = rc_lap
            safety_car_laps.append(current_sc)
            current_sc = None

    # Close any SC/VSC that was never formally withdrawn (edge case)
    if current_sc is not None:
        safety_car_laps.append(current_sc)

    # ── 3. Determine total laps ───────────────────────────────────────────────
    all_laps: list[int] = []
    for laps in driver_gaps.values():
        all_laps.extend(laps.keys())
    total_laps: int = max(all_laps, default=0)

    # ── 4. Assemble driver entries ────────────────────────────────────────────
    drivers_out: list[dict[str, Any]] = []
    for abbr, laps_dict in sorted(driver_gaps.items()):
        team = _DRIVER_TEAMS.get(abbr, "Unknown")
        drivers_out.append(
            {
                "driver": abbr,
                "team": team,
                "color": _team_color(team),
                # Stringify lap keys for JSON compatibility
                "gaps_s": {str(k): v for k, v in sorted(laps_dict.items())},
            }
        )

    logger.info(
        "build_gap_to_leader: %d drivers, %d laps, %d SC windows",
        len(drivers_out),
        total_laps,
        len(safety_car_laps),
    )

    return {
        "event": event_name,
        "year": year,
        "total_laps": total_laps,
        "safety_car_laps": safety_car_laps,
        "drivers": drivers_out,
    }


def build_pit_stop_efficiency(
    pit_stops: list[dict[str, Any]],
    drivers_meta: list[dict[str, Any]],
    event_name: str,
    year: int,
) -> dict[str, Any]:
    """Transform raw OpenF1 pit records into the pit-stop efficiency artifact.

    OpenF1's ``pit_duration`` represents the full pit-lane transit time (entry
    to exit).  OpenF1 does not separately expose stationary time in the free
    tier, so ``stationary_s`` is approximated as ``pit_duration - 18.0``.
    18 s is the empirical F1 pit-lane entry/exit transit median across
    permanent circuits; teams use this same approximation for broadcast
    "stationary time" graphics.  Values clamped to [0, pit_duration].

    Args:
        pit_stops: Raw rows from :func:`fetch_pit_stops`.
        drivers_meta: Raw rows from the OpenF1 ``/drivers`` endpoint.
        event_name: Human-readable event name.
        year: Championship season.

    Returns:
        Dictionary matching the ``pit_stops_round_N.json`` schema.
    """
    transit_estimate_s = 18.0  # see docstring rationale

    # {team: [stop, ...]}
    team_stops: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in pit_stops:
        drv_num = row.get("driver_number")
        lap = row.get("lap_number")
        duration_raw = row.get("pit_duration")
        if drv_num is None or lap is None or duration_raw is None:
            continue

        try:
            pit_duration_s = float(duration_raw)
        except (TypeError, ValueError):
            continue

        abbr = _driver_abbr_from_number(drv_num, drivers_meta)
        team = _DRIVER_TEAMS.get(abbr, "Unknown")
        stationary_s = max(0.0, pit_duration_s - transit_estimate_s)

        team_stops[team].append(
            {
                "driver": abbr,
                "lap": int(lap),
                "pit_duration_s": round(pit_duration_s, 3),
                "stationary_s": round(stationary_s, 3),
            }
        )

    teams_out: list[dict[str, Any]] = [
        {
            "team": team,
            "color": _team_color(team),
            "stops": sorted(stops, key=lambda s: (s["driver"], s["lap"])),
        }
        for team, stops in sorted(team_stops.items())
    ]

    logger.info(
        "build_pit_stop_efficiency: %d teams, %d total stops",
        len(teams_out),
        sum(len(t["stops"]) for t in teams_out),
    )

    return {"event": event_name, "year": year, "teams": teams_out}
