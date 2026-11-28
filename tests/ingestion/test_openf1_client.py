"""Unit tests for the OpenF1 API client and artifact builders."""

from __future__ import annotations

from unittest.mock import patch

from f1_predictions.ingestion.openf1_client import (
    build_gap_to_leader,
    build_pit_stop_efficiency,
    get_session_key,
)


def test_get_session_key_returns_none_on_empty_response() -> None:
    """Empty session list from OpenF1 should return None cleanly."""
    with patch("f1_predictions.ingestion.openf1_client._get", return_value=[]):
        assert get_session_key(2026, 22) is None


def test_get_session_key_returns_int_when_found() -> None:
    """Valid OpenF1 /sessions row should resolve to integer session_key."""
    sample = [{"session_key": 9912, "meeting_name": "Qatar Grand Prix"}]
    with patch("f1_predictions.ingestion.openf1_client._get", return_value=sample):
        assert get_session_key(2026, 22) == 9912


def test_build_gap_to_leader_maps_sc_and_drivers() -> None:
    """Safety Car windows and per-driver gaps should map into the expected schema."""
    intervals = [
        {"driver_number": 1, "lap_number": 1, "gap_to_leader": "0.0"},
        {"driver_number": 1, "lap_number": 2, "gap_to_leader": "0.0"},
        {"driver_number": 4, "lap_number": 1, "gap_to_leader": "+1.450"},
        {"driver_number": 4, "lap_number": 2, "gap_to_leader": "+2.100"},
        {"driver_number": 4, "lap_number": 3, "gap_to_leader": "1 LAP"},
    ]
    race_control = [
        {
            "date": "2026-11-29T17:10:00Z",
            "lap_number": 10,
            "message": "SAFETY CAR DEPLOYED",
        },
        {
            "date": "2026-11-29T17:15:00Z",
            "lap_number": 13,
            "message": "SAFETY CAR IN THIS LAP",
        },
        {
            "date": "2026-11-29T17:25:00Z",
            "lap_number": 20,
            "message": "VIRTUAL SAFETY CAR DEPLOYED",
        },
        {
            "date": "2026-11-29T17:27:00Z",
            "lap_number": 21,
            "message": "VIRTUAL SAFETY CAR ENDING",
        },
    ]
    drivers_meta = [
        {"driver_number": 1, "name_acronym": "VER"},
        {"driver_number": 4, "name_acronym": "NOR"},
    ]

    result = build_gap_to_leader(
        intervals=intervals,
        race_control=race_control,
        drivers_meta=drivers_meta,
        event_name="Qatar Grand Prix",
        year=2026,
    )

    assert result["event"] == "Qatar Grand Prix"
    assert result["year"] == 2026
    assert result["total_laps"] == 3
    assert result["safety_car_laps"] == [
        {"start_lap": 10, "end_lap": 13, "type": "SC"},
        {"start_lap": 20, "end_lap": 21, "type": "VSC"},
    ]

    drivers_by_code = {d["driver"]: d for d in result["drivers"]}
    assert drivers_by_code["VER"]["gaps_s"] == {"1": 0.0, "2": 0.0}
    assert drivers_by_code["NOR"]["gaps_s"] == {"1": 1.45, "2": 2.1, "3": 999.0}
    assert drivers_by_code["NOR"]["team"] == "McLaren"


def test_build_pit_stop_efficiency_aggregates_by_team() -> None:
    """Pit stops should be grouped by team with stationary time clamped >= 0."""
    pit_stops = [
        {"driver_number": 4, "lap_number": 18, "pit_duration": 21.45},
        {"driver_number": 81, "lap_number": 20, "pit_duration": 20.80},
        {"driver_number": 1, "lap_number": 15, "pit_duration": 16.50},
    ]
    drivers_meta = [
        {"driver_number": 4, "name_acronym": "NOR"},
        {"driver_number": 81, "name_acronym": "PIA"},
        {"driver_number": 1, "name_acronym": "VER"},
    ]

    result = build_pit_stop_efficiency(
        pit_stops=pit_stops,
        drivers_meta=drivers_meta,
        event_name="Qatar Grand Prix",
        year=2026,
    )

    teams = {t["team"]: t for t in result["teams"]}
    assert len(teams["McLaren"]["stops"]) == 2
    assert teams["McLaren"]["stops"][0] == {
        "driver": "NOR",
        "lap": 18,
        "pit_duration_s": 21.45,
        "stationary_s": 3.45,
    }
    # Transit estimate is 18.0 s, so 16.50 s clamps stationary_s to 0.0
    assert teams["Red Bull Racing"]["stops"][0]["stationary_s"] == 0.0
