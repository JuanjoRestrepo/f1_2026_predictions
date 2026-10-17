"""Fail when the dashboard cannot render the next race on the official calendar.

The main page greys out any round whose artifacts are missing and shows
"Awaiting Data" instead of a link. That is the correct behaviour for a race the
season has not reached, but it is a silent regression when the season data simply
stopped being regenerated — the page looks healthy while the next race is
unreachable.

This check mirrors the dashboard's own availability rule (see
``f1_predictions.utils.calendar_coverage``) and exits non-zero when:

* the next race on the calendar has no artifacts, or
* a race that has already been run has no artifacts.

Future rounds beyond the next race are reported but never fail the check, since
they legitimately have no data yet.

Usage::

    uv run python scripts/check_next_race_coverage.py
    uv run python scripts/check_next_race_coverage.py --today 2026-10-25
    uv run python scripts/check_next_race_coverage.py --json

Exit codes:
    0 - the next race (and every completed race) is renderable
    1 - a coverage gap, or the calendar could not be read
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from f1_predictions.utils.calendar_coverage import (
    CalendarRace,
    CoverageReport,
    assess_coverage,
)


def format_rounds(rounds: tuple[int, ...]) -> str:
    """Collapse round numbers into a compact range string.

    Args:
        rounds: Ascending round numbers.

    Returns:
        e.g. ``"1-18"``, ``"1-3, 7, 9-12"``, or ``"-"`` when empty.
    """
    if not rounds:
        return "-"

    ordered = sorted(rounds)
    parts: list[str] = []
    start = previous = ordered[0]
    for number in ordered[1:]:
        if number == previous + 1:
            previous = number
            continue
        parts.append(f"{start}-{previous}" if start != previous else f"{start}")
        start = previous = number
    parts.append(f"{start}-{previous}" if start != previous else f"{start}")
    return ", ".join(parts)


def describe(race: CalendarRace) -> str:
    """Render a race for a log line."""
    return f"R{race.round} {race.name} ({race.date.isoformat()})"


def render_report(report: CoverageReport, reference: date) -> str:
    """Build the human-readable coverage summary.

    Args:
        report: Coverage assessment.
        reference: Date the assessment was made against.

    Returns:
        A multi-line report.
    """
    next_race = report.next_race
    next_line = (
        f"{describe(next_race)} [{'COVERED' if report.next_race_covered else 'MISSING'}]"
        if next_race
        else "season complete"
    )

    lines = [
        f"F1 {report.season} calendar coverage (reference date: {reference.isoformat()})",
        "",
        f"  next race            {next_line}",
        f"  calendar rounds      {report.calendar_size}",
        f"  covered              {format_rounds(report.covered_rounds)}"
        f" ({len(report.covered_rounds)}/{report.calendar_size})",
        f"  completed, no data   "
        f"{format_rounds(tuple(r.round for r in report.completed_without_data))}",
        f"  upcoming, no data    "
        f"{format_rounds(tuple(r.round for r in report.upcoming_without_data))}"
        f" (expected until predicted)",
    ]
    return "\n".join(lines)


def render_gap(report: CoverageReport) -> str:
    """Explain a coverage gap and how to close it."""
    lines = ["", "COVERAGE GAP — the dashboard cannot render these races:"]
    missing = list(report.completed_without_data)
    if report.next_race and not report.next_race_covered:
        missing.insert(0, report.next_race)

    for race in missing:
        lines.append(f"  {describe(race)}")
    lines.extend(
        [
            "",
            "Generate the missing artifacts with the offline simulator:",
            "",
            *(
                f'  uv run python scripts/simulate_race.py --year {report.season} '
                f'--round {race.round} --event "{race.name}"'
                for race in missing
            ),
            "",
            "Then republish the bundle: databricks_entrypoint.py --run-mode export",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the coverage guard."""
    parser = argparse.ArgumentParser(
        description="Verify the dashboard can render the next race on the calendar.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--season", type=int, default=2026, help="Season year.")
    parser.add_argument(
        "--reports-dir", type=Path, default=Path("reports"), help="Reports root."
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        help="Reference date (YYYY-MM-DD); defaults to today. Use for deterministic runs.",
    )
    parser.add_argument(
        "--only-next-race",
        action="store_true",
        help="Ignore gaps for races that have already been run.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    """Run the coverage guard and report the outcome."""
    args = parse_args()
    reference = args.today or date.today()
    report = assess_coverage(args.reports_dir, args.season, reference)

    if report.calendar_size == 0:
        print(
            f"error: no calendar found at "
            f"{args.reports_dir / str(args.season) / 'calendar.json'} — "
            f"run the sync_calendar workflow first.",
            file=sys.stderr,
        )
        return 1

    passed = report.next_race_covered and (
        args.only_next_race or not report.completed_without_data
    )

    if args.json:
        print(
            json.dumps(
                {
                    "season": report.season,
                    "reference_date": reference.isoformat(),
                    "calendar_size": report.calendar_size,
                    "covered_rounds": list(report.covered_rounds),
                    "next_race": (
                        {
                            "round": report.next_race.round,
                            "name": report.next_race.name,
                            "date": report.next_race.date.isoformat(),
                            "covered": report.next_race_covered,
                        }
                        if report.next_race
                        else None
                    ),
                    "completed_without_data": [
                        race.round for race in report.completed_without_data
                    ],
                    "upcoming_without_data": [
                        race.round for race in report.upcoming_without_data
                    ],
                    "ok": passed,
                },
                indent=2,
            )
        )
        return 0 if passed else 1

    print(render_report(report, reference))
    if passed:
        print("\nCoverage OK — the dashboard can render the next race.")
        return 0

    print(render_gap(report))
    return 1


if __name__ == "__main__":
    sys.exit(main())
