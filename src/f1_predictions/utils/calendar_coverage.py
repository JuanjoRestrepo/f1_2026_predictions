"""Calendar coverage checks for the dashboard bundle.

The main page renders every round in ``reports/<season>/calendar.json`` and marks
a round *available* when either of these is true:

1. a file under ``summaries/`` has ``round_<N>`` in its name, or
2. ``<calendar dir>/results/predictions.csv`` exists.

That rule lives in ``dashboard/src/utils/fileReader.ts`` (``getAvailableRaces``).
This module mirrors it so the pipeline can assert the invariant the UI depends on:
the *next* race on the official calendar must be reachable, because both the hero
card and the calendar grid link to it. A round with no artifacts renders as a
greyed-out "Awaiting Data" tile, which is what silently happens when the season
data stops being regenerated.

Keep the two implementations aligned — if the TypeScript rule changes, change it
here as well. ``tests/unit/test_calendar_coverage.py`` pins this behaviour.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from f1_predictions.utils.dashboard_publish import season_directory

# The dashboard scans summaries/ file names for this pattern, so we match it
# exactly rather than requiring a specific artifact name.
_ROUND_IN_FILENAME = re.compile(r"round_(\d+)")

# The calendar's directory names and the on-disk layout disagree for this pair
# (both refer to the same circuit). The dashboard compensates, so we must too.
_DIRECTORY_ALIASES: dict[str, tuple[str, ...]] = {
    "Barcelona_Grand_Prix": ("Spanish_Grand_Prix",),
    "Spanish_Grand_Prix": ("Barcelona_Grand_Prix",),
}


@dataclass(frozen=True)
class CalendarRace:
    """A single round of the season calendar.

    Attributes:
        round: Round number as published in the calendar.
        name: Display name, e.g. "United States Grand Prix".
        directory: On-disk directory under ``reports/<season>/``.
        date: Race day.
        event_format: FastF1 event format, e.g. "conventional" or "sprint".
    """

    round: int
    name: str
    directory: str
    date: date
    event_format: str = ""


@dataclass(frozen=True)
class CoverageReport:
    """Which calendar rounds the dashboard can actually render.

    Attributes:
        season: Season year the report describes.
        calendar_size: Number of rounds in the calendar.
        next_race: The next race on or after the reference date, if any.
        covered_rounds: Rounds with at least one dashboard artifact.
        completed_without_data: Races already run that have no artifacts.
        upcoming_without_data: Future races that have no artifacts yet.
    """

    season: int
    calendar_size: int
    next_race: CalendarRace | None
    covered_rounds: tuple[int, ...]
    completed_without_data: tuple[CalendarRace, ...]
    upcoming_without_data: tuple[CalendarRace, ...]

    @property
    def next_race_covered(self) -> bool:
        """Return True when the next race has artifacts, or the season is over."""
        return self.next_race is None or self.next_race.round in self.covered_rounds

    @property
    def ok(self) -> bool:
        """Return True when the next race and every completed race are available."""
        return self.next_race_covered and not self.completed_without_data


def load_calendar(reports_dir: Path, season: int) -> list[CalendarRace]:
    """Load ``reports/<season>/calendar.json``.

    Args:
        reports_dir: Root ``reports`` directory.
        season: F1 season year.

    Returns:
        Calendar races in ascending round order. Empty when the file is absent
        (normal during initial local development) so callers degrade gracefully
        instead of raising, matching the dashboard's behaviour.
    """
    calendar_path = season_directory(reports_dir, season) / "calendar.json"
    if not calendar_path.is_file():
        return []

    payload = json.loads(calendar_path.read_text(encoding="utf-8"))
    races = [
        CalendarRace(
            round=int(entry["round"]),
            name=str(entry.get("name") or f"Round {entry['round']}"),
            directory=str(entry.get("dir") or f"Round_{entry['round']}"),
            date=date.fromisoformat(str(entry["date"])),
            event_format=str(entry.get("event_format", "")),
        )
        for entry in payload.get("races", [])
    ]
    return sorted(races, key=lambda race: race.round)


def covered_rounds(
    reports_dir: Path,
    season: int,
    calendar: Sequence[CalendarRace],
) -> set[int]:
    """Return the round numbers the dashboard can serve.

    Args:
        reports_dir: Root ``reports`` directory.
        season: F1 season year.
        calendar: Calendar races, used to resolve on-disk directory names.

    Returns:
        Round numbers that have either a ``summaries/`` artifact or a
        ``results/predictions.csv``, matching ``getAvailableRaces``.
    """
    season_dir = season_directory(reports_dir, season)
    covered: set[int] = set()

    summaries_dir = season_dir / "summaries"
    if summaries_dir.is_dir():
        for entry in summaries_dir.iterdir():
            match = _ROUND_IN_FILENAME.search(entry.name)
            if match:
                covered.add(int(match.group(1)))

    for race in calendar:
        candidates = (race.directory, *_DIRECTORY_ALIASES.get(race.directory, ()))
        for directory in candidates:
            if (season_dir / directory / "results" / "predictions.csv").is_file():
                covered.add(race.round)
                break

    return covered


def next_race(calendar: Sequence[CalendarRace], today: date) -> CalendarRace | None:
    """Return the first race on or after ``today``.

    The dashboard compares the end of each race day against the start of today,
    which for date-only calendar entries is the same as ``race.date >= today``.

    Args:
        calendar: Calendar races in round order.
        today: Reference date.

    Returns:
        The next race, or None once the season is complete.
    """
    return next((race for race in calendar if race.date >= today), None)


def assess_coverage(
    reports_dir: Path,
    season: int,
    today: date | None = None,
) -> CoverageReport:
    """Summarise which rounds are renderable and whether that is acceptable.

    Args:
        reports_dir: Root ``reports`` directory.
        season: F1 season year.
        today: Reference date; defaults to the current date. Exposed so the
            nightly pipeline and tests stay deterministic.

    Returns:
        A :class:`CoverageReport` for the season.
    """
    reference = today or date.today()
    calendar = load_calendar(reports_dir, season)
    covered = covered_rounds(reports_dir, season, calendar)

    return CoverageReport(
        season=season,
        calendar_size=len(calendar),
        next_race=next_race(calendar, reference),
        covered_rounds=tuple(sorted(covered)),
        completed_without_data=tuple(
            race
            for race in calendar
            if race.date < reference and race.round not in covered
        ),
        upcoming_without_data=tuple(
            race
            for race in calendar
            if race.date >= reference and race.round not in covered
        ),
    )
