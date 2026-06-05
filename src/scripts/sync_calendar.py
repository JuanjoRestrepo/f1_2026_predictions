"""Sync the official F1 event schedule to a JSON calendar file.

Rationale:
    Hardcoding the season calendar in the dashboard TypeScript codebase is
    fragile — FIA regularly adjusts race dates and the order of rounds. This
    script fetches the canonical schedule directly from FastF1 (which in turn
    uses the official Ergast/F1 API data), normalises it into a stable JSON
    format, and writes it to `reports/<season>/calendar.json`.

    The dashboard's fileReader.ts reads from this file at build-time, so the
    frontend always reflects the correct, up-to-date race order and dates. Run
    this script as part of the weekly data-refresh CI job to stay in sync.

Usage:
    uv run python src/scripts/sync_calendar.py              # defaults to 2026
    uv run python src/scripts/sync_calendar.py --season 2025

Exit codes:
    0 — success
    1 — FastF1 fetch failure or IO error
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import fastf1

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_SEASON: int = 2026
# Relative to repo root (where uv run is invoked)
REPORTS_DIR: Path = Path("reports")
CALENDAR_FILENAME: str = "calendar.json"

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Convert an event name to a title-cased underscore slug.

    Example:
        "Canadian Grand Prix" -> "Canadian_Grand_Prix"
        "São Paulo Grand Prix" -> "Sao_Paulo_Grand_Prix"

    Args:
        name: The human-readable GP name from FastF1.

    Returns:
        A filesystem-safe slug string.
    """
    # Normalise common unicode substitutions that appear in F1 calendars.
    replacements: dict[str, str] = {
        "ã": "a",
        "â": "a",
        "à": "a",
        "á": "a",
        "ä": "a",
        "ç": "c",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "í": "i",
        "ì": "i",
        "ï": "i",
        "ó": "o",
        "ò": "o",
        "ô": "o",
        "ö": "o",
        "ú": "u",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ñ": "n",
    }
    result = name
    for char, replacement in replacements.items():
        result = result.replace(char, replacement)
        result = result.replace(char.upper(), replacement.upper())

    # Replace non-alphanumeric characters (except underscores) with underscores,
    # then collapse any multiple consecutive underscores.
    result = re.sub(r"[^\w]", "_", result)
    result = re.sub(r"_+", "_", result).strip("_")
    return result


def fetch_schedule(season: int) -> list[dict[str, str | int]]:
    """Fetch the F1 event schedule for the given season via FastF1.

    Filters out pre-season testing sessions (round 0) and returns only
    race-weekend events in round order.

    Args:
        season: The F1 season year (e.g. 2026).

    Returns:
        A list of dicts with keys:
            - round (int): FIA round number.
            - name (str): Official GP name (e.g. "Canadian Grand Prix").
            - dir (str): Filesystem slug (e.g. "Canadian_Grand_Prix").
            - date (str): ISO-8601 date string in UTC (e.g. "2026-05-24").
            - event_format (str): "conventional", "sprint", or "testing".

    Raises:
        RuntimeError: If the FastF1 API returns an empty or invalid schedule.
    """
    logger.info("Fetching FastF1 event schedule for %d season...", season)
    raw: fastf1.events.EventSchedule = fastf1.get_event_schedule(
        season, include_testing=False
    )

    if raw.empty:
        raise RuntimeError(
            f"FastF1 returned an empty schedule for season {season}. "
            "The season data may not yet be published."
        )

    events: list[dict[str, str | int]] = []
    for _, row in raw.iterrows():
        round_num = int(row["RoundNumber"])
        if round_num == 0:
            # Pre-season testing — skip (include_testing=False should already
            # exclude these, but we guard defensively).
            continue

        event_date = row["EventDate"]
        # FastF1 returns tz-naive or tz-aware timestamps depending on the SDK
        # version. Normalise to a plain ISO date string (YYYY-MM-DD) for
        # portable JSON consumption by the TypeScript dashboard.
        if hasattr(event_date, "isoformat"):
            date_str = event_date.strftime("%Y-%m-%d")
        else:
            date_str = str(event_date)[:10]

        events.append(
            {
                "round": round_num,
                "name": str(row["EventName"]),
                "dir": _slugify(str(row["EventName"])),
                "date": date_str,
                "event_format": str(row.get("EventFormat", "conventional")).lower(),
            }
        )

    events.sort(key=lambda e: int(e["round"]))  # type: ignore[arg-type]
    logger.info("Fetched %d race events for the %d season.", len(events), season)
    return events


def write_calendar(season: int, events: list[dict[str, str | int]]) -> Path:
    """Persist the calendar events to `reports/<season>/calendar.json`.

    The output JSON schema is intentionally compatible with the TypeScript
    `RaceInfo` interface in `dashboard/src/utils/fileReader.ts`.

    Args:
        season: The F1 season year.
        events: List of event dicts from `fetch_schedule`.

    Returns:
        The absolute path to the written file.

    Raises:
        OSError: If the target directory cannot be created or file cannot be
            written.
    """
    out_dir = REPORTS_DIR / str(season)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / CALENDAR_FILENAME

    payload: dict[str, object] = {
        "season": season,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source": "fastf1",
        "races": events,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Calendar written to %s", out_path)
    return out_path


def main() -> None:
    """Entry point: parse args, fetch schedule, write JSON."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Sync the official F1 event schedule to calendar.json."
    )
    parser.add_argument(
        "--season",
        type=int,
        default=DEFAULT_SEASON,
        help=f"F1 season year to sync (default: {DEFAULT_SEASON}).",
    )
    args = parser.parse_args()

    try:
        events = fetch_schedule(args.season)
        out_path = write_calendar(args.season, events)
        print(f"✅  calendar.json updated: {out_path}")
        print(f"    {len(events)} races for the {args.season} season.")
        for evt in events:
            print(f"    Round {evt['round']:>2d}: {evt['name']} ({evt['date']})")
    except Exception as exc:
        logger.error("Calendar sync failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
