"""Unit tests for the Jolpica F1 API client."""

from __future__ import annotations

from unittest.mock import patch

from f1_predictions.ingestion.jolpica_client import (
    build_championship_standings,
    fetch_constructor_standings,
    fetch_driver_standings,
)


def test_fetch_driver_standings_parses_ergast_payload() -> None:
    """Driver standings should be extracted from MRData.StandingsTable."""
    payload = {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "DriverStandings": [
                            {
                                "position": "1",
                                "points": "390",
                                "Driver": {"code": "VER", "familyName": "Verstappen"},
                                "Constructors": [{"name": "Red Bull"}],
                            }
                        ]
                    }
                ]
            }
        }
    }
    target = "f1_predictions.ingestion.jolpica_client._get_json"
    with patch(target, return_value=payload):
        rows = fetch_driver_standings(2026, 22)

    assert len(rows) == 1
    assert rows[0]["Driver"]["code"] == "VER"


def test_fetch_constructor_standings_handles_empty_list() -> None:
    """Empty StandingsLists should return an empty list without raising."""
    payload = {"MRData": {"StandingsTable": {"StandingsLists": []}}}
    target = "f1_predictions.ingestion.jolpica_client._get_json"
    with patch(target, return_value=payload):
        assert fetch_constructor_standings(2026, 22) == []


def test_build_championship_standings_normalizes_teams_and_drivers() -> None:
    """Team aliases, rookie codes, and colors should be normalized."""
    driver_rows = [
        {
            "position": "1",
            "points": "350",
            "Driver": {"code": "NOR", "familyName": "Norris"},
            "Constructors": [{"name": "McLaren"}],
        },
        {
            "position": "2",
            "points": "310",
            "Driver": {"code": "", "familyName": "Antonelli"},
            "Constructors": [{"name": "Mercedes"}],
        },
    ]
    constructor_rows = [
        {
            "position": "1",
            "points": "640",
            "Constructor": {"name": "McLaren"},
        },
        {
            "position": "2",
            "points": "520",
            "Constructor": {"name": "Red Bull"},
        },
    ]

    result = build_championship_standings(
        driver_standings=driver_rows,
        constructor_standings=constructor_rows,
        event_name="Qatar Grand Prix",
        year=2026,
        round_number=22,
    )

    assert result["event"] == "Qatar Grand Prix"
    assert result["year"] == 2026
    assert result["round"] == 22
    assert result["drivers"][0] == {
        "position": 1,
        "driver": "NOR",
        "team": "McLaren",
        "color": "#FF8000",
        "points": 350.0,
    }
    assert result["drivers"][1]["driver"] == "ANT"
    assert result["constructors"][1]["team"] == "Red Bull Racing"
    assert result["constructors"][1]["color"] == "#3671C6"
