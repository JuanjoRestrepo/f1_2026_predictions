"""Shared feature-contract tests (Task 21.3).

These tests pin the bridge between the local 70-feature Gold and the opt-in
Databricks lap table: schema resolution, version gating, NaN policy and the
prediction output shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from f1_predictions.features.contract import (
    AGGREGATE_SCHEMA,
    FEATURE_CONTRACT_VERSION,
    LAP_FEATURES,
    LAP_SCHEMA,
    VERSION_COLUMN,
    resolve_training_schema,
    validate_feature_frame,
)
from f1_predictions.features.training_data import (
    build_prediction_frame,
    prepare_feature_frame,
    prepare_training_data,
)


def _lap_frame(rows: int = 4) -> pd.DataFrame:
    """Build a minimal frame matching the lap contract."""
    records: list[dict[str, object]] = []
    for index in range(rows):
        record: dict[str, object] = dict.fromkeys(LAP_FEATURES, 0.0)
        record.update(
            {
                "Season": 2026,
                "RoundNumber": 3,
                "EventName": "Japanese Grand Prix",
                "Driver": "VER",
                "LapNumber": index + 1,
                "Stint": 1,
                "LapTime_s": 90.0 + index,
                VERSION_COLUMN: FEATURE_CONTRACT_VERSION,
                "Compound": "SOFT",
                "Team": "Red Bull",
                "Position": index + 1,
                "SessionType": "Race",
                "TyreLife": float(index + 1),
                "roll_laptime_3": 90.0 + index,
                "roll_laptime_5": 90.5 + index,
                "roll_std_3": 0.1,
                "delta_roll_pace": -0.5,
                "delta_to_fastest_s": 0.2,
                "Compound_SOFT": 1.0,
            }
        )
        records.append(record)
    return pd.DataFrame(records)


def _aggregate_frame() -> pd.DataFrame:
    """Build a minimal legacy aggregate frame."""
    return pd.DataFrame(
        {
            "Season": [2026, 2026],
            "EventName": ["Japanese Grand Prix", "Bahrain Grand Prix"],
            "Driver": ["VER", "NOR"],
            "total_laps": [50, 48],
            "mean_pace_seconds": [90.1, 90.2],
            "pace_std_seconds": [0.4, 0.5],
            "tyre_degradation_slope": [0.03, 0.04],
            "fastest_lap_seconds": [88.9, 89.0],
        }
    )


def test_resolve_training_schema_defaults_to_aggregate() -> None:
    assert resolve_training_schema(None) is AGGREGATE_SCHEMA
    assert resolve_training_schema("aggregate") is AGGREGATE_SCHEMA


def test_resolve_training_schema_returns_lap() -> None:
    assert resolve_training_schema("lap") is LAP_SCHEMA


def test_resolve_training_schema_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown training schema"):
        resolve_training_schema("qualifying")


def test_lap_schema_is_versioned_and_does_not_fill_missing() -> None:
    assert LAP_SCHEMA.contract_version == FEATURE_CONTRACT_VERSION
    assert LAP_SCHEMA.fill_missing_features is False
    assert LAP_SCHEMA.cv_group_columns == ("Season", "RoundNumber")
    assert LAP_SCHEMA.model_name == "xgb_lap_pace_regressor"


def test_validate_feature_frame_accepts_lap_contract() -> None:
    validate_feature_frame(_lap_frame(), LAP_SCHEMA)


def test_validate_feature_frame_rejects_missing_feature() -> None:
    frame = _lap_frame().drop(columns=["roll_laptime_3"])

    with pytest.raises(ValueError, match="roll_laptime_3"):
        validate_feature_frame(frame, LAP_SCHEMA)


def test_validate_feature_frame_requires_version_column() -> None:
    frame = _lap_frame().drop(columns=[VERSION_COLUMN])

    with pytest.raises(ValueError, match=VERSION_COLUMN):
        validate_feature_frame(frame, LAP_SCHEMA)


def test_validate_feature_frame_allows_versionless_local_gold() -> None:
    frame = _lap_frame().drop(columns=[VERSION_COLUMN])

    validate_feature_frame(frame, LAP_SCHEMA, require_version=False)


def test_validate_feature_frame_target_is_optional_for_scoring() -> None:
    frame = _lap_frame().drop(columns=["LapTime_s"])

    with pytest.raises(ValueError, match="LapTime_s"):
        validate_feature_frame(frame, LAP_SCHEMA)
    validate_feature_frame(frame, LAP_SCHEMA, require_target=False)


def test_validate_feature_frame_rejects_non_frame() -> None:
    with pytest.raises(TypeError, match="columns"):
        validate_feature_frame([1, 2, 3], LAP_SCHEMA)


def test_prepare_training_data_lap_preserves_nan_features() -> None:
    frame = _lap_frame()
    frame.loc[0, "roll_laptime_3"] = float("nan")

    data = prepare_training_data(frame, LAP_SCHEMA)

    assert len(data.X) == len(frame)
    assert pd.isna(data.X.loc[0, "roll_laptime_3"])
    assert data.dropped_target_rows == 0
    assert data.groups is not None
    assert data.groups.tolist() == ["2026|3"] * len(frame)


def test_prepare_training_data_drops_null_target_rows() -> None:
    frame = _lap_frame()
    frame.loc[1, "LapTime_s"] = float("nan")

    data = prepare_training_data(frame, LAP_SCHEMA)

    assert len(data.X) == len(frame) - 1
    assert len(data.y) == len(frame) - 1
    assert data.dropped_target_rows == 1
    assert 1 not in set(data.y.index)


def test_prepare_training_data_groups_by_event() -> None:
    frame = _lap_frame(rows=8)
    frame.loc[4:, "RoundNumber"] = 4
    frame.loc[4:, "EventName"] = "Bahrain Grand Prix"

    data = prepare_training_data(frame, LAP_SCHEMA)

    assert data.groups is not None
    assert data.groups.tolist().count("2026|3") == 4
    assert data.groups.tolist().count("2026|4") == 4


def test_prepare_training_data_rejects_version_mismatch() -> None:
    frame = _lap_frame()
    frame[VERSION_COLUMN] = 999

    with pytest.raises(ValueError, match="feature_contract_version"):
        prepare_training_data(frame, LAP_SCHEMA)


def test_prepare_training_data_rejects_non_numeric_feature() -> None:
    frame = _lap_frame()
    frame["Compound_SOFT"] = "soft"

    with pytest.raises(ValueError, match="non-numeric"):
        prepare_training_data(frame, LAP_SCHEMA)


def test_prepare_training_data_aggregate_fills_nan() -> None:
    frame = _aggregate_frame()
    frame.loc[0, "mean_pace_seconds"] = float("nan")

    data = prepare_training_data(frame, AGGREGATE_SCHEMA)

    assert data.X.loc[0, "mean_pace_seconds"] == 0.0
    assert data.groups is None
    assert data.dropped_target_rows == 0


def test_prepare_training_data_rejects_empty_frame() -> None:
    frame = _lap_frame(rows=1).iloc[0:0]

    with pytest.raises(ValueError, match="no rows"):
        prepare_training_data(frame, LAP_SCHEMA)


def test_prepare_feature_frame_does_not_require_target() -> None:
    frame = _lap_frame().drop(columns=["LapTime_s"])

    matrix = prepare_feature_frame(frame, LAP_SCHEMA)

    assert list(matrix.columns) == list(LAP_FEATURES)
    assert len(matrix) == len(frame)
    assert matrix.dtypes.tolist() == [float] * len(LAP_FEATURES)


def test_prepare_feature_frame_leaves_lap_nan_intact() -> None:
    frame = _lap_frame()
    frame.loc[0, "roll_laptime_3"] = float("nan")

    matrix = prepare_feature_frame(frame, LAP_SCHEMA)

    assert pd.isna(matrix.loc[0, "roll_laptime_3"])


def test_build_prediction_frame_carries_keys_and_metadata() -> None:
    frame = _lap_frame(rows=3)
    scored_at = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)

    output = build_prediction_frame(
        frame,
        [90.1, 90.2, 90.3],
        LAP_SCHEMA,
        model_name=LAP_SCHEMA.model_name,
        scored_at_utc=scored_at,
    )

    assert list(output.columns) == [
        "Season",
        "RoundNumber",
        "EventName",
        "Driver",
        "LapNumber",
        "Stint",
        "prediction",
        "model_name",
        "scored_at_utc",
    ]
    assert output["prediction"].tolist() == [90.1, 90.2, 90.3]
    assert set(output["model_name"]) == {LAP_SCHEMA.model_name}
    assert set(output["scored_at_utc"]) == {scored_at.isoformat()}


def test_build_prediction_frame_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="prediction"):
        build_prediction_frame(
            _lap_frame(rows=3),
            [90.1],
            LAP_SCHEMA,
            model_name=LAP_SCHEMA.model_name,
        )


@pytest.mark.integration
def test_local_gold_schema_contains_bridge_features() -> None:
    """The union of local Gold files must expose every shared feature."""
    import pyarrow.parquet as pq

    files = sorted(Path("data/outputs/laps").glob("season=*/round=*/*.parquet"))
    if not files:
        pytest.skip("local Gold layer not present")

    available: set[str] = set()
    for path in files:
        available.update(pq.read_schema(path).names)

    missing = set(LAP_FEATURES) - available
    assert not missing, f"local Gold is missing bridge features: {sorted(missing)}"
