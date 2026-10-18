"""Unit tests for f1_predictions.features.traffic_exposure."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from f1_predictions.features.traffic_exposure import (
    CLEAN_AIR_SCENARIO,
    TRAFFIC_COLUMNS,
    add_traffic_exposure,
)


def _frame(
    rows: list[tuple[str, float, float, float, float]],
    *,
    event: str = "Test Grand Prix",
    lap_time_column: str = "LapTime_s",
) -> pd.DataFrame:
    """Build a Gold-shaped lap frame from (driver, lap, start, end, lap_time)."""
    df = pd.DataFrame(
        {
            "Season": 2025,
            "RoundNumber": 1,
            "EventName": event,
            "Driver": [r[0] for r in rows],
            "LapNumber": [r[1] for r in rows],
            "LapStartTime": pd.to_timedelta([r[2] for r in rows], unit="s"),
            "Time": pd.to_timedelta([r[3] for r in rows], unit="s"),
            "LapTime_s": [r[4] for r in rows],
        }
    )
    if lap_time_column != "LapTime_s":
        df[lap_time_column] = df.pop("LapTime_s")
    return df


def _labels(laps: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Label a synthetic session, then index the results by driver."""
    labelled = add_traffic_exposure(laps)
    return {
        str(row.Driver): {
            "ahead": float(row.traffic_ahead_s),
            "nearest": float(row.traffic_nearest_s),
            "clean": float(row.in_clean_air),
        }
        for row in labelled.itertuples()
    }


# ── Geometry: the margins must mean what they claim to mean ───────────────────


def test_gap_to_car_ahead_is_measured_in_seconds_of_track_distance() -> None:
    """A car that starts one second later is exactly one second behind."""
    labelled = _labels(
        _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 1.0, 101.0, 100.0)])
    )

    assert labelled["HAM"]["ahead"] == pytest.approx(1.0, abs=1e-6)
    assert labelled["HAM"]["nearest"] == pytest.approx(1.0, abs=1e-6)
    # The car in front sees the same one-second gap, but as an approach from
    # behind: nothing is ahead of it within a lap.
    assert labelled["VER"]["ahead"] == pytest.approx(99.0, abs=1e-6)
    assert labelled["VER"]["nearest"] == pytest.approx(1.0, abs=1e-6)


def test_margins_scale_with_the_session_reference_lap() -> None:
    """One lap of track distance is worth the session's median lap time.

    Monza laps are ~80 s and Singapore laps are ~100 s, so the same lap-fraction
    offset is worth different gaps. A fixed global constant would mis-scale one
    of them.
    """
    short = _labels(
        _frame([("VER", 1, 0.0, 100.0, 200.0), ("HAM", 1, 1.0, 101.0, 200.0)])
    )
    assert short["HAM"]["ahead"] == pytest.approx(2.0, abs=1e-6)

    long = _labels(
        _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 1.0, 101.0, 100.0)])
    )
    assert long["HAM"]["ahead"] == pytest.approx(1.0, abs=1e-6)


def test_cars_racing_apart_are_both_clean() -> None:
    """A five-second gap leaves both cars in clean air at a 100 s lap."""
    labelled = _labels(
        _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 5.0, 105.0, 100.0)])
    )

    assert labelled["HAM"]["ahead"] == pytest.approx(5.0, abs=1e-6)
    assert labelled["HAM"]["nearest"] == pytest.approx(5.0, abs=1e-6)
    assert labelled["HAM"]["clean"] == 1.0
    assert labelled["VER"]["ahead"] == pytest.approx(95.0, abs=1e-6)
    assert labelled["VER"]["nearest"] == pytest.approx(5.0, abs=1e-6)
    assert labelled["VER"]["clean"] == 1.0


def test_following_inside_two_seconds_is_not_clean_air() -> None:
    """The measured dirty-air penalty is live below 2.0 s, so the flag fires."""
    labelled = _labels(
        _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 1.5, 101.5, 100.0)])
    )

    assert labelled["HAM"]["ahead"] == pytest.approx(1.5, abs=1e-6)
    assert labelled["HAM"]["clean"] == 0.0


def test_a_car_just_behind_also_breaks_clean_air() -> None:
    """Nearest-car distance is symmetric, so the leader is not clean either.

    The leader has nothing ahead of it within a lap, so only the nearest-car
    threshold can flag the car behind it.
    """
    labelled = _labels(
        _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 1.0, 101.0, 100.0)])
    )

    assert labelled["VER"]["ahead"] > 2.0
    assert labelled["VER"]["nearest"] == pytest.approx(1.0, abs=1e-6)
    assert labelled["VER"]["clean"] == 0.0


def test_traffic_is_computed_against_the_nearest_of_several_cars() -> None:
    """With three cars in a train, each sees its own nearest neighbour."""
    labelled = _labels(
        _frame(
            [
                ("VER", 1, 0.0, 100.0, 100.0),
                ("HAM", 1, 2.0, 102.0, 100.0),
                ("LEC", 1, 8.0, 108.0, 100.0),
            ]
        )
    )

    assert labelled["HAM"]["ahead"] == pytest.approx(2.0, abs=1e-6)
    assert labelled["LEC"]["ahead"] == pytest.approx(6.0, abs=1e-6)
    assert labelled["VER"]["nearest"] == pytest.approx(2.0, abs=1e-6)


def test_lapped_traffic_is_measured_forward_from_the_focal_car() -> None:
    """A lapped car ahead on track is still ahead of the leader.

    Progress is counted in laps since the start and read modulo one lap, so a
    car one lap down that is physically half a lap up the road is reported as
    half a lap ahead of the leader rather than a full lap and a half behind it.
    """
    labelled = _labels(
        _frame([("VER", 2, 100.0, 200.0, 100.0), ("HAM", 1, 50.0, 150.0, 100.0)])
    )

    assert labelled["VER"]["nearest"] == pytest.approx(50.0, abs=1e-6)
    assert labelled["VER"]["ahead"] == pytest.approx(50.0, abs=1e-6)
    assert labelled["HAM"]["nearest"] == pytest.approx(50.0, abs=1e-6)
    assert labelled["HAM"]["clean"] == 1.0


# ── Contract: shape, dtypes, degradation ─────────────────────────────────────


def test_rows_and_order_are_preserved() -> None:
    """The function is a column-adder, not a filter or re-sorter."""
    df = _frame(
        [
            ("HAM", 2, 5.0, 105.0, 100.0),
            ("VER", 1, 0.0, 100.0, 100.0),
            ("HAM", 1, 0.0, 100.0, 100.0),
        ]
    )
    labelled = add_traffic_exposure(df)

    assert len(labelled) == len(df)
    assert labelled.index.equals(df.index)
    assert list(labelled["Driver"]) == list(df["Driver"])
    assert list(labelled["LapNumber"]) == list(df["LapNumber"])
    assert set(TRAFFIC_COLUMNS).issubset(labelled.columns)


def test_labels_are_numeric_for_the_gold_contract() -> None:
    """The Gold layer admits numeric features only."""
    labelled = add_traffic_exposure(
        _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 1.0, 101.0, 100.0)])
    )

    for column in TRAFFIC_COLUMNS:
        assert pd.api.types.is_numeric_dtype(labelled[column])


def test_input_frame_is_not_mutated() -> None:
    """Callers keep the frame they passed in."""
    df = _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 1.0, 101.0, 100.0)])
    before = list(df.columns)

    add_traffic_exposure(df)

    assert list(df.columns) == before


def test_unusable_interval_is_labelled_nan_without_disturbing_the_others() -> None:
    """A 300 s 'lap' is a stoppage; its position cannot be trusted."""
    labelled = _labels(
        _frame(
            [
                ("VER", 1, 0.0, 100.0, 100.0),
                ("HAM", 1, 5.0, 105.0, 100.0),
                ("LEC", 1, 2000.0, 2300.0, 300.0),
            ]
        )
    )

    assert np.isnan(labelled["LEC"]["ahead"])
    assert np.isnan(labelled["LEC"]["clean"])
    assert labelled["HAM"]["ahead"] == pytest.approx(5.0, abs=1e-6)
    assert labelled["VER"]["nearest"] == pytest.approx(5.0, abs=1e-6)


def test_single_car_session_reports_unknown_rather_than_clean() -> None:
    """With nobody else on track there is no exposure to measure."""
    labelled = _labels(
        _frame([("VER", 1, 0.0, 100.0, 100.0), ("VER", 2, 100.0, 200.0, 100.0)])
    )

    for lap in labelled.values():
        assert np.isnan(lap["ahead"])
        assert np.isnan(lap["nearest"])
        assert np.isnan(lap["clean"])


def test_session_without_lap_times_falls_back_to_offsets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A round with no usable lap times still yields margins, from durations."""
    df = _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 5.0, 105.0, 100.0)])
    df["LapTime_s"] = np.nan

    with caplog.at_level(logging.WARNING):
        labelled = _labels(add_traffic_exposure(df))

    assert labelled["HAM"]["ahead"] == pytest.approx(5.0, abs=1e-6)


def test_frame_without_any_timing_degrades_to_nan_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No intervals means no labels, and the log has to say so."""
    df = _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 1.0, 101.0, 100.0)])
    df["LapStartTime"] = pd.NaT

    with caplog.at_level(logging.WARNING):
        labelled = add_traffic_exposure(df)

    assert labelled["traffic_ahead_s"].isna().all()
    assert labelled["in_clean_air"].isna().all()
    assert any("not computable" in r.getMessage() for r in caplog.records)


def test_offsets_already_in_seconds_are_accepted() -> None:
    """Silver/Gold carry timedeltas, but float seconds must work too."""
    df = _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 5.0, 105.0, 100.0)])
    df["start_seconds"] = df["LapStartTime"].dt.total_seconds()
    df["end_seconds"] = df["Time"].dt.total_seconds()

    labelled = _labels(
        add_traffic_exposure(df, start_col="start_seconds", end_col="end_seconds")
    )

    assert labelled["HAM"]["ahead"] == pytest.approx(5.0, abs=1e-6)


# ── Guards against misuse ────────────────────────────────────────────────────


def test_mixed_events_are_rejected() -> None:
    """Session-relative offsets are not comparable across sessions."""
    df = _frame([("VER", 1, 0.0, 100.0, 100.0), ("HAM", 1, 5.0, 105.0, 100.0)])
    df.loc[1, "EventName"] = "Another Grand Prix"

    with pytest.raises(ValueError, match="single session"):
        add_traffic_exposure(df)


def test_missing_column_raises_keyerror() -> None:
    """A missing timing column is a caller bug, not a data gap."""
    df = _frame([("VER", 1, 0.0, 100.0, 100.0)]).drop(columns=["Time"])

    with pytest.raises(KeyError, match="Time"):
        add_traffic_exposure(df)


def test_non_dataframe_raises_typeerror() -> None:
    """Type check happens before any column access."""
    with pytest.raises(TypeError, match=r"Expected pd\.DataFrame"):
        add_traffic_exposure([("VER", 1)])


def test_clean_air_scenario_is_physically_consistent() -> None:
    """The served scenario must be a valid clean-air lap, not an extreme.

    ``traffic_nearest_s`` is a minimum over both directions, so it can never
    exceed ``traffic_ahead_s``.
    """
    assert set(CLEAN_AIR_SCENARIO) == set(TRAFFIC_COLUMNS)
    assert CLEAN_AIR_SCENARIO["in_clean_air"] == 1.0
    assert (
        CLEAN_AIR_SCENARIO["traffic_nearest_s"] <= CLEAN_AIR_SCENARIO["traffic_ahead_s"]
    )


# ── Data-gated: the labels must keep measuring real dirty air ────────────────

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "outputs" / "laps"
_lap_files = sorted(_DATA_DIR.glob("season=*/**/*.parquet"))


@pytest.mark.skipif(not _lap_files, reason="local lap data not ingested")
def test_real_laps_show_dirty_air_decaying_with_the_gap() -> None:
    """Guard the meaning of the labels against real race data.

    Paired within (driver, stint) against the nearest clean-air lap, tyre age and
    fuel load are held roughly constant, so what remains is traffic. On the
    ingested calendar the penalty is largest close behind a car and has decayed
    to nothing by the 1.5-2.0 s bucket. If the label ever stops showing that
    ordering it is measuring something other than traffic.
    """
    frames = []
    for path in _lap_files:
        laps = pd.read_parquet(path)
        labelled = add_traffic_exposure(laps)
        for (_driver, _stint), group in labelled.groupby(["Driver", "Stint"]):
            clean = group[group["in_clean_air"] == 1.0]
            if len(clean) < 2:
                continue
            trailing = group[
                (group["in_clean_air"] == 0.0) & group["traffic_ahead_s"].notna()
            ]
            if trailing.empty:
                continue
            lap_numbers = clean["LapNumber"].to_numpy(dtype=float)
            paces = clean["LapTime_s"].to_numpy(dtype=float)
            for row in trailing.itertuples():
                nearest = int(np.argmin(np.abs(lap_numbers - float(row.LapNumber))))
                if abs(lap_numbers[nearest] - float(row.LapNumber)) > 2.0:
                    continue
                frames.append(
                    {
                        "ahead": float(row.traffic_ahead_s),
                        "penalty": float(row.LapTime_s) - paces[nearest],
                    }
                )

    paired = pd.DataFrame(frames)
    assert len(paired) > 200, "expected a broad reference set of traffic laps"

    close = paired[paired["ahead"] < 0.5]["penalty"].median()
    far = paired[paired["ahead"].between(1.0, 2.0)]["penalty"].median()

    assert close > 0.0
    assert close > far
