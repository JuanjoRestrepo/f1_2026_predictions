"""Unit tests for the Unity Catalog Volume ingestion helpers."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from f1_predictions.databricks.volume_ingest import (
    BRONZE_LAP_COLUMNS,
    build_bronze_laps,
    completed_round_numbers,
    round_volume_path,
    schema_location,
    volume_root,
)


def _fastf1_laps() -> pd.DataFrame:
    """Minimal FastF1-shaped laps frame (LapTime as timedelta)."""
    return pd.DataFrame(
        {
            "Driver": ["VER", "VER", "NOR"],
            "LapNumber": [1.0, 2.0, 1.0],
            "LapTime": pd.to_timedelta(
                ["0 days 00:01:30.500", "0 days 00:01:29.100", "0 days 00:01:31.000"]
            ),
            "Compound": ["SOFT", "SOFT", "MEDIUM"],
            "TyreLife": [1.0, 2.0, 1.0],
            "Stint": [1.0, 1.0, 1.0],
            "Team": ["Red Bull", "Red Bull", "McLaren"],
            "Position": [1.0, 2.0, 1.0],
        }
    )


def test_build_bronze_laps_converts_timedelta_to_seconds() -> None:
    """FastF1 timedelta LapTime must become float seconds."""
    bronze = build_bronze_laps(
        _fastf1_laps(), season=2026, round_number=3, event_name="Japanese Grand Prix"
    )

    # Sorted by Driver then LapNumber: NOR(1)=91.0, VER(1)=90.5, VER(2)=89.1.
    assert bronze["LapTime"].tolist() == pytest.approx([91.0, 90.5, 89.1])
    assert bronze["LapTime"].dtype == "float64"


def test_build_bronze_laps_stamps_metadata_from_args() -> None:
    """Season/Round/Session/Event come from the caller, not the source frame."""
    source = _fastf1_laps()
    source["Season"] = 1999  # deliberately wrong — must be overwritten
    source["EventName"] = "Wrong GP"

    bronze = build_bronze_laps(
        source, season=2026, round_number=11, event_name="British Grand Prix"
    )

    assert set(bronze["Season"]) == {2026}
    assert set(bronze["EventName"]) == {"British Grand Prix"}
    assert set(bronze["RoundNumber"]) == {11}
    assert set(bronze["SessionType"]) == {"Race"}


def test_build_bronze_laps_returns_exact_contract_sorted() -> None:
    """Output columns match the Bronze contract and are driver/lap sorted."""
    bronze = build_bronze_laps(
        _fastf1_laps(), season=2026, round_number=3, event_name="Japanese Grand Prix"
    )

    assert list(bronze.columns) == list(BRONZE_LAP_COLUMNS)
    # Sorted by Driver then LapNumber (NOR before VER).
    assert bronze["Driver"].tolist() == ["NOR", "VER", "VER"]
    assert bronze["LapNumber"].tolist() == [1, 1, 2]
    assert bronze["Stint"].tolist() == [1, 1, 1]
    assert bronze["Team"].tolist() == ["McLaren", "Red Bull", "Red Bull"]
    assert bronze["Position"].tolist() == [1, 1, 2]


def test_build_bronze_laps_drops_rows_without_valid_lap_or_driver() -> None:
    """Rows missing a driver, lap number, or lap time are dropped."""
    source = pd.DataFrame(
        {
            "Driver": ["VER", None, "NOR"],
            "LapNumber": [1.0, 2.0, None],
            "LapTime": pd.to_timedelta(
                ["0 days 00:01:30", "0 days 00:01:31", "0 days 00:01:32"]
            ),
        }
    )

    bronze = build_bronze_laps(
        source, season=2026, round_number=1, event_name="Bahrain Grand Prix"
    )

    assert bronze["Driver"].tolist() == ["VER"]


def test_build_bronze_laps_accepts_numeric_laptime() -> None:
    """A numeric (already-seconds) LapTime is passed through unchanged."""
    source = pd.DataFrame({"Driver": ["VER"], "LapNumber": [1], "LapTime": [88.25]})

    bronze = build_bronze_laps(
        source, season=2026, round_number=1, event_name="Bahrain Grand Prix"
    )

    assert bronze["LapTime"].iloc[0] == pytest.approx(88.25)


def test_build_bronze_laps_fills_optional_columns_when_absent() -> None:
    """Missing optional lap context is surfaced as NULL, not dropped."""
    source = pd.DataFrame(
        {
            "Driver": ["VER"],
            "LapNumber": [1],
            "LapTime": pd.to_timedelta(["0 days 00:01:30"]),
        }
    )

    bronze = build_bronze_laps(
        source, season=2026, round_number=1, event_name="Bahrain Grand Prix"
    )

    assert bronze["Compound"].isna().all()
    assert bronze["TyreLife"].isna().all()
    assert bronze["Stint"].isna().all()
    assert bronze["Team"].isna().all()
    assert bronze["Position"].isna().all()


def test_dlt_bronze_columns_match_ingest_contract() -> None:
    """The DLT notebook's select list must not drift from the writer contract."""
    pipeline = Path("src/f1_predictions/databricks/pipelines/f1_medallion_pipeline.py")
    tree = ast.parse(pipeline.read_text(encoding="utf-8"))

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "_BRONZE_COLUMNS" in names:
            assert tuple(ast.literal_eval(node.value)) == BRONZE_LAP_COLUMNS
            return

    pytest.fail("_BRONZE_COLUMNS not found in the DLT pipeline")


def test_dlt_bronze_uses_uc_compatible_source_metadata() -> None:
    """Unity Catalog rejects input_file_name(); use _metadata.file_path."""
    pipeline = Path("src/f1_predictions/databricks/pipelines/f1_medallion_pipeline.py")
    tree = ast.parse(pipeline.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    assert not any(
        isinstance(call.func, ast.Attribute) and call.func.attr == "input_file_name"
        for call in calls
    )
    assert any(
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "col"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "_metadata.file_path"
        for call in calls
    )


def test_dlt_silver_dedupes_reingested_laps() -> None:
    """Bronze appends on re-ingest, so Silver must collapse duplicate laps."""
    pipeline = Path("src/f1_predictions/databricks/pipelines/f1_medallion_pipeline.py")
    tree = ast.parse(pipeline.read_text(encoding="utf-8"))

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "dedupe_laps" in imported

    silver = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "laps_silver"
    )
    called = {
        call.func.id
        for call in ast.walk(silver)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }
    assert "dedupe_laps" in called


def test_build_bronze_laps_raises_on_empty_input() -> None:
    """An empty source frame is a programming error, not an empty result."""
    with pytest.raises(ValueError, match="empty DataFrame"):
        build_bronze_laps(
            pd.DataFrame(), season=2026, round_number=1, event_name="Bahrain GP"
        )


def test_build_bronze_laps_raises_on_missing_core_columns() -> None:
    """Missing Driver/LapNumber/LapTime must fail loudly."""
    with pytest.raises(KeyError, match="required Bronze columns"):
        build_bronze_laps(
            pd.DataFrame({"Driver": ["VER"]}),
            season=2026,
            round_number=1,
            event_name="Bahrain GP",
        )


def test_build_bronze_laps_raises_when_no_rows_survive() -> None:
    """All-invalid input (e.g. missing lap timing) raises rather than writing junk."""
    source = pd.DataFrame(
        {
            "Driver": ["VER"],
            "LapNumber": [1],
            "LapTime": [pd.NaT],
        }
    )

    with pytest.raises(ValueError, match="No valid laps remained"):
        build_bronze_laps(source, season=2026, round_number=1, event_name="Bahrain GP")


def test_path_helpers_reflect_volume_layout() -> None:
    """Volume paths follow /Volumes/<catalog>/<schema>/raw_telemetry/... layout."""
    assert volume_root("main", "race_pace") == "/Volumes/main/race_pace/raw_telemetry"
    assert (
        round_volume_path("main", "race_pace", 2026, 3)
        == "/Volumes/main/race_pace/raw_telemetry/season=2026/round=03"
    )
    assert (
        schema_location("main", "race_pace")
        == "/Volumes/main/race_pace/raw_telemetry/_schema"
    )


def test_completed_round_numbers_filters_future_and_testing() -> None:
    """Only races dated on/before now, excluding testing events, are returned."""
    schedule = pd.DataFrame(
        {
            "RoundNumber": [1, 2, 3, 4],
            "EventDate": pd.to_datetime(
                ["2026-03-01", "2026-03-15", "2026-04-01", "2026-02-01"], utc=True
            ),
            "EventFormat": ["Race", "Race", "Race", "testing"],
        }
    )

    rounds = completed_round_numbers(
        schedule, now_utc=datetime(2026, 3, 20, tzinfo=UTC)
    )

    assert rounds == [1, 2]


def test_completed_round_numbers_handles_empty_schedule() -> None:
    """An empty schedule yields no rounds rather than raising."""
    assert completed_round_numbers(pd.DataFrame()) == []
