"""Unit tests for the calendar coverage rule and its CLI guard.

The rule mirrors ``getAvailableRaces`` in ``dashboard/src/utils/fileReader.ts``:
a round is renderable when a ``summaries/`` file name contains ``round_<N>`` or
``<calendar dir>/results/predictions.csv`` exists. If these tests drift from the
TypeScript, the dashboard will grey out races the pipeline believes it published —
which is exactly the silent failure the guard exists to prevent.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from f1_predictions.utils.calendar_coverage import (
    CalendarRace,
    assess_coverage,
    covered_rounds,
    load_calendar,
    next_race,
)
from scripts.check_next_race_coverage import format_rounds, main

_AUSTRALIA = {
    "round": 1,
    "name": "Australian Grand Prix",
    "dir": "Australian_Grand_Prix",
    "date": "2026-03-08",
    "event_format": "conventional",
}
_SPANISH = {
    "round": 2,
    "name": "Spanish Grand Prix",
    "dir": "Spanish_Grand_Prix",
    "date": "2026-05-10",
    "event_format": "conventional",
}
_US_GP = {
    "round": 3,
    "name": "United States Grand Prix",
    "dir": "United_States_Grand_Prix",
    "date": "2026-10-25",
    "event_format": "sprint",
}


def _write_calendar(tmp_path: Path, races: list[dict[str, object]]) -> Path:
    """Create ``reports/2026/calendar.json`` and return the reports root."""
    reports = tmp_path / "reports"
    (reports / "2026").mkdir(parents=True)
    (reports / "2026" / "calendar.json").write_text(
        json.dumps(
            {
                "season": 2026,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "source": "fastf1",
                "races": races,
            }
        ),
        encoding="utf-8",
    )
    return reports


def _add_summary(reports: Path, filename: str) -> None:
    summaries = reports / "2026" / "summaries"
    summaries.mkdir(parents=True, exist_ok=True)
    (summaries / filename).write_text("{}", encoding="utf-8")


def _add_predictions(reports: Path, directory: str) -> None:
    results = reports / "2026" / directory / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / "predictions.csv").write_text(
        "Driver,predicted_laptime_xgb_s\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Calendar loading
# ---------------------------------------------------------------------------


def test_load_calendar_parses_and_sorts_by_round(tmp_path: Path) -> None:
    """Rounds come back in ascending order with typed fields."""
    reports = _write_calendar(tmp_path, [_US_GP, _AUSTRALIA, _SPANISH])

    races = load_calendar(reports, 2026)

    assert [r.round for r in races] == [1, 2, 3]
    assert races[0].name == "Australian Grand Prix"
    assert races[0].directory == "Australian_Grand_Prix"
    assert races[0].date == date(2026, 3, 8)
    assert races[2].event_format == "sprint"


def test_load_calendar_missing_file_returns_empty(tmp_path: Path) -> None:
    """A missing calendar degrades to an empty list rather than raising."""
    assert load_calendar(tmp_path / "reports", 2026) == []


def test_load_calendar_tolerates_missing_optional_fields(tmp_path: Path) -> None:
    """A minimal entry still yields a usable race."""
    reports = _write_calendar(tmp_path, [{"round": 5, "date": "2026-07-05"}])

    race = load_calendar(reports, 2026)[0]

    assert race.name == "Round 5"
    assert race.directory == "Round_5"
    assert race.event_format == ""


# ---------------------------------------------------------------------------
# The availability rule
# ---------------------------------------------------------------------------


def test_covered_rounds_reads_summaries_filenames(tmp_path: Path) -> None:
    """Any summaries/ file containing round_N marks that round available."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA, _SPANISH, _US_GP])
    _add_summary(reports, "predicted_report_round_1.md")
    _add_summary(reports, "tyre_intelligence_round_1.json")
    _add_summary(reports, "report_round_3.md")
    _add_summary(reports, "season_overview.md")

    covered = covered_rounds(reports, 2026, load_calendar(reports, 2026))

    assert covered == {1, 3}


def test_covered_rounds_reads_predictions_csv(tmp_path: Path) -> None:
    """A race directory with predictions.csv marks that round available."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA, _SPANISH, _US_GP])
    _add_predictions(reports, "Australian_Grand_Prix")

    covered = covered_rounds(reports, 2026, load_calendar(reports, 2026))

    assert covered == {1}


def test_covered_rounds_honours_the_barcelona_spanish_alias(tmp_path: Path) -> None:
    """The calendar and on-disk directory disagree for this pair; both count."""
    reports = _write_calendar(tmp_path, [_SPANISH])
    _add_predictions(reports, "Barcelona_Grand_Prix")

    covered = covered_rounds(reports, 2026, load_calendar(reports, 2026))

    assert covered == {2}


def test_covered_rounds_ignores_directories_not_in_the_calendar(tmp_path: Path) -> None:
    """Stray leftovers on disk must not invent rounds."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA])
    _add_predictions(reports, "Nowhere_Grand_Prix")

    assert covered_rounds(reports, 2026, load_calendar(reports, 2026)) == set()


# ---------------------------------------------------------------------------
# Next race selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("today", "expected_round"),
    [
        (date(2026, 1, 1), 1),  # before the season
        (date(2026, 3, 7), 1),  # day before race day
        (date(2026, 3, 8), 1),  # on race day — still "next"
        (date(2026, 3, 9), 2),  # day after
        (date(2026, 10, 25), 3),  # on the final race day
        (date(2026, 10, 26), None),  # season over
    ],
)
def test_next_race_boundaries(today: date, expected_round: int | None) -> None:
    """Race day itself counts as upcoming; the day after it has passed."""
    calendar = [
        CalendarRace(
            1, "Australian Grand Prix", "Australian_Grand_Prix", date(2026, 3, 8)
        ),
        CalendarRace(2, "Spanish Grand Prix", "Spanish_Grand_Prix", date(2026, 5, 10)),
        CalendarRace(
            3,
            "United States Grand Prix",
            "United_States_Grand_Prix",
            date(2026, 10, 25),
        ),
    ]

    race = next_race(calendar, today)

    assert (race.round if race else None) == expected_round


# ---------------------------------------------------------------------------
# Coverage assessment
# ---------------------------------------------------------------------------


def test_assess_coverage_ok_when_next_race_is_renderable(tmp_path: Path) -> None:
    """A covered next race with no completed gaps passes."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA, _SPANISH, _US_GP])
    _add_summary(reports, "report_round_1.md")
    _add_summary(reports, "report_round_2.md")
    _add_summary(reports, "predicted_report_round_3.md")

    report = assess_coverage(reports, 2026, date(2026, 10, 17))

    assert report.next_race is not None
    assert report.next_race.round == 3
    assert report.next_race_covered is True
    assert report.ok is True


def test_assess_coverage_flags_missing_next_race(tmp_path: Path) -> None:
    """The regression this guard exists for: next race unreachable."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA, _SPANISH, _US_GP])
    _add_summary(reports, "predicted_report_round_1.md")

    report = assess_coverage(reports, 2026, date(2026, 10, 17))

    assert report.next_race_covered is False
    assert report.ok is False
    # R2 is in the past and also uncovered - reported separately.
    assert [r.round for r in report.completed_without_data] == [2]
    assert [r.round for r in report.upcoming_without_data] == [3]


def test_assess_coverage_reports_completed_gap_even_when_next_is_covered(
    tmp_path: Path,
) -> None:
    """A skipped completed race is a gap even if the upcoming one is fine."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA, _SPANISH, _US_GP])
    _add_summary(reports, "report_round_1.md")
    _add_summary(reports, "predicted_report_round_3.md")

    report = assess_coverage(reports, 2026, date(2026, 10, 17))

    assert report.next_race_covered is True
    assert [r.round for r in report.completed_without_data] == [2]
    assert report.ok is False


def test_assess_coverage_ok_once_the_season_is_over(tmp_path: Path) -> None:
    """No next race means nothing to render, so nothing to fail."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA])
    _add_summary(reports, "report_round_1.md")

    report = assess_coverage(reports, 2026, date(2026, 12, 31))

    assert report.next_race is None
    assert report.next_race_covered is True
    assert report.ok is True


def test_assess_coverage_with_no_calendar_is_empty(tmp_path: Path) -> None:
    """A missing calendar yields a zero-size report the CLI rejects."""
    report = assess_coverage(tmp_path / "reports", 2026, date(2026, 10, 17))

    assert report.calendar_size == 0
    assert report.covered_rounds == ()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rounds", "expected"),
    [
        ((), "-"),
        ((4,), "4"),
        ((1, 2, 3), "1-3"),
        ((1, 2, 3, 7), "1-3, 7"),
        ((1, 2, 9, 10, 11, 20), "1-2, 9-11, 20"),
    ],
)
def test_format_rounds_collapses_ranges(rounds: tuple[int, ...], expected: str) -> None:
    """Gap listings stay readable regardless of season length."""
    assert format_rounds(rounds) == expected


def _run_cli(
    reports: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
) -> tuple[int, str]:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check",
            "--reports-dir",
            str(reports),
            "--season",
            "2026",
            "--today",
            "2026-10-17",
            *extra,
        ],
    )
    code = main()
    return code, capsys.readouterr().out


def test_cli_passes_when_the_next_race_is_covered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A healthy bundle exits 0 and names the race."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA, _US_GP])
    _add_summary(reports, "report_round_1.md")
    _add_summary(reports, "predicted_report_round_3.md")

    code, out = _run_cli(reports, monkeypatch, capsys)

    assert code == 0
    assert "United States Grand Prix" in out
    assert "Coverage OK" in out


def test_cli_fails_and_prints_the_fix_when_data_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A gap exits 1 with the exact command that closes it."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA, _US_GP])
    _add_summary(reports, "report_round_1.md")

    code, out = _run_cli(reports, monkeypatch, capsys)

    assert code == 1
    assert "COVERAGE GAP" in out
    assert "scripts/simulate_race.py --year 2026 --round 3" in out
    assert '--event "United States Grand Prix"' in out


def test_cli_only_next_race_ignores_completed_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--only-next-race relaxes the check for historical gaps."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA, _SPANISH, _US_GP])
    _add_summary(reports, "predicted_report_round_3.md")

    code, _ = _run_cli(reports, monkeypatch, capsys, "--only-next-race")

    assert code == 0


def test_cli_json_output_is_machine_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--json exposes the assessment for the pipeline."""
    reports = _write_calendar(tmp_path, [_AUSTRALIA, _US_GP])
    _add_summary(reports, "report_round_1.md")
    _add_summary(reports, "predicted_report_round_3.md")

    code, out = _run_cli(reports, monkeypatch, capsys, "--json")

    payload = json.loads(out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["next_race"] == {
        "round": 3,
        "name": "United States Grand Prix",
        "date": "2026-10-25",
        "covered": True,
    }


def test_cli_rejects_a_missing_calendar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without a calendar the check cannot pass, so it must not exit 0."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["check", "--reports-dir", str(tmp_path / "reports"), "--today", "2026-10-17"],
    )

    assert main() == 1
    assert "no calendar found" in capsys.readouterr().err
