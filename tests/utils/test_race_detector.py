"""Unit tests for the race_detector module.

Tests are fully self-contained: no FastF1 network calls are made.
The `get_event_schedule` function is mocked to inject deterministic
DataFrames, ensuring tests run fast and offline.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from f1_predictions.utils.race_detector import find_last_completed_race


def _make_schedule(
    events: list[tuple[str, str, int]],
) -> pd.DataFrame:
    """Build a minimal event schedule DataFrame for testing.

    Args:
        events: List of (event_name, event_date_iso, round_number) tuples.

    Returns:
        DataFrame matching the FastF1 schedule schema.
    """
    rows = []
    for name, date_str, rnd in events:
        rows.append(
            {
                "EventName": name,
                "EventDate": date_str,
                "RoundNumber": rnd,
                "EventFormat": "conventional",
            }
        )
    return pd.DataFrame(rows)


class TestFindLastCompletedRace:
    """Tests for the pure `find_last_completed_race` function."""

    def test_detects_race_yesterday(self) -> None:
        """Should return race metadata when a race was 1 day ago."""
        now = datetime(2026, 5, 26, 9, 0, tzinfo=UTC)  # Monday 09:00
        schedule = _make_schedule(
            [
                ("Monaco Grand Prix", "2026-05-25T14:00:00+00:00", 8),  # Sunday
            ]
        )
        result = find_last_completed_race(schedule, now_utc=now, days_back=2)

        assert result is not None
        assert result["round"] == 8
        assert "Monaco" in result["gp_name"]

    def test_returns_none_when_no_recent_race(self) -> None:
        """Should return None when no race is within the lookback window."""
        now = datetime(2026, 5, 26, 9, 0, tzinfo=UTC)
        schedule = _make_schedule(
            [
                ("Spanish Grand Prix", "2026-05-18T14:00:00+00:00", 7),  # 8 days ago
            ]
        )
        result = find_last_completed_race(schedule, now_utc=now, days_back=2)

        assert result is None

    def test_ignores_future_races(self) -> None:
        """Should not return races scheduled in the future."""
        now = datetime(2026, 5, 26, 9, 0, tzinfo=UTC)
        schedule = _make_schedule(
            [
                ("Canadian Grand Prix", "2026-06-14T14:00:00+00:00", 9),  # Future
            ]
        )
        result = find_last_completed_race(schedule, now_utc=now, days_back=2)

        assert result is None

    def test_ignores_testing_events(self) -> None:
        """Should not match pre-season testing events."""
        now = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
        schedule = pd.DataFrame(
            [
                {
                    "EventName": "Pre-Season Testing",
                    "EventDate": "2026-03-01T08:00:00+00:00",
                    "RoundNumber": 0,
                    "EventFormat": "testing",
                }
            ]
        )
        result = find_last_completed_race(schedule, now_utc=now, days_back=2)

        assert result is None

    def test_picks_most_recent_from_multiple(self) -> None:
        """Should return the most recent race when multiple fall in window."""
        now = datetime(2026, 5, 27, 9, 0, tzinfo=UTC)
        schedule = _make_schedule(
            [
                ("Old Race", "2026-05-25T14:00:00+00:00", 7),
                ("Newer Race", "2026-05-26T14:00:00+00:00", 8),  # More recent
            ]
        )
        result = find_last_completed_race(schedule, now_utc=now, days_back=3)

        assert result is not None
        assert result["round"] == 8

    def test_empty_schedule_returns_none(self) -> None:
        """Should return None for an empty schedule DataFrame."""
        now = datetime(2026, 5, 26, 9, 0, tzinfo=UTC)
        schedule = _make_schedule([])
        result = find_last_completed_race(schedule, now_utc=now)

        assert result is None

    def test_result_contains_required_keys(self) -> None:
        """Result dict should always contain 'round', 'gp_name', 'event_date'."""
        now = datetime(2026, 5, 26, 9, 0, tzinfo=UTC)
        schedule = _make_schedule(
            [
                ("Monaco Grand Prix", "2026-05-25T14:00:00+00:00", 8),
            ]
        )
        result = find_last_completed_race(schedule, now_utc=now, days_back=2)

        assert result is not None
        assert "round" in result
        assert "gp_name" in result
        assert "event_date" in result
