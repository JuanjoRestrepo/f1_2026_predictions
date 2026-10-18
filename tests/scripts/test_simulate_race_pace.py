"""Unit tests for the pace normalisation in scripts/simulate_race.py.

The simulator translates a driver's season median onto the target circuit's
lap-time scale. That translation used to subtract a *pooled* season median, which
mostly measures which circuits a driver happened to have laps at: the current-season
window mixes circuits whose lap times differ by more than ten seconds, so a driver
with no laps at a short track read as seconds per lap slower than a team-mate with no
laps at a long one.

Sector times and speeds arrive through exactly the same door and carried the same
artefact, worse: across the current window the pooled sector spread is 12-16x the
per-circuit spread, against 2.8x for lap time. Both are corrected here.

These tests pin the corrected behaviour: pace is measured against each round's own
baseline, one observation per round, so track mix cannot masquerade as pace.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import pandas as pd
import pytest

from f1_predictions.features.traffic_exposure import CLEAN_AIR_SCENARIO
from f1_predictions.models.common import prepare_feature_matrix
from scripts.simulate_race import (
    _apply_track_pace_normalization,
    _build_simulation_scenario,
    _current_form_stats,
    _driver_track_normalized_deltas,
    _gold_files_before_round,
    check_published_dispersion,
)

_FAST_DRIVER = "FAST"
_SLOW_DRIVER = "SLOW"


def _laps(rows: list[tuple[str, int, float, bool]]) -> pd.DataFrame:
    """Build a lap frame from ``(driver, round, lap_time, rainy)`` tuples."""
    return pd.DataFrame(
        [
            {"Driver": driver, "RoundNumber": rnd, "LapTime_s": time, "Rainfall": wet}
            for driver, rnd, time, wet in rows
        ]
    )


def _current_laps() -> pd.DataFrame:
    """A two-circuit window with deliberately unbalanced lap counts.

    Round 1 is a short circuit (~80s), round 2 a long one (~100s). The fast
    driver has eight laps at the short circuit and only two at the long one; the
    slow driver is the other way round.
    """
    return _laps(
        [(_FAST_DRIVER, 1, 80.0, False)] * 8
        + [(_SLOW_DRIVER, 1, 81.0, False)] * 8
        + [(_FAST_DRIVER, 2, 100.5, False)] * 2
        + [(_SLOW_DRIVER, 2, 100.0, False)] * 8
    )


def _sim(drivers: list[str]) -> pd.DataFrame:
    """A simulation scenario with the pace columns the normaliser writes to."""
    return pd.DataFrame(
        [
            {
                "Driver": driver,
                "roll_laptime_3": 90.0,
                "roll_laptime_5": 90.0,
                "Sector1Time_s": 30.0,
                "Sector2Time_s": 31.0,
                "Sector3Time_s": 29.0,
            }
            for driver in drivers
        ]
    )


def _gold(event: str, lap_time: float) -> pd.DataFrame:
    """Historical laps for a target circuit, at a known baseline."""
    return pd.DataFrame(
        [{"EventName": event, "LapTime_s": lap_time, "Rainfall": False}] * 20
    )


def test_pooled_median_is_confounded_but_per_track_delta_is_not() -> None:
    """The whole point of the fix, in one assertion pair."""
    current = _current_laps()

    deltas = _driver_track_normalized_deltas(current, is_wet_race=False)
    assert deltas[_FAST_DRIVER] == pytest.approx(0.0)
    assert deltas[_SLOW_DRIVER] == pytest.approx(0.25)
    assert deltas.max() - deltas.min() == pytest.approx(0.25)

    # What the old code used: a median pooled across both circuits, which puts
    # these two drivers 10.5s apart purely because of lap-count mix.
    pooled = current.groupby("Driver")["LapTime_s"].median()
    assert pooled[_SLOW_DRIVER] - pooled[_FAST_DRIVER] == pytest.approx(10.5)


def test_target_pace_is_the_track_baseline_plus_the_driver_delta() -> None:
    """The delta lands on the target circuit's level, not the window's."""
    out = _apply_track_pace_normalization(
        _sim([_FAST_DRIVER, _SLOW_DRIVER]),
        "Canada Grand Prix",
        _gold("Canada Grand Prix", 78.0),
        _current_laps(),
        is_wet_race=False,
    ).set_index("Driver")

    assert out.loc[_FAST_DRIVER, "roll_laptime_3"] == pytest.approx(78.0)
    assert out.loc[_SLOW_DRIVER, "roll_laptime_3"] == pytest.approx(78.25)
    # roll_laptime_5 mirrors roll_laptime_3, as before.
    assert out.loc[_FAST_DRIVER, "roll_laptime_5"] == pytest.approx(78.0)


def test_sectors_are_scaled_once_for_the_whole_field() -> None:
    """Sector scale is a circuit-to-circuit ratio, not a per-driver fudge."""
    current = _current_laps()
    out = _apply_track_pace_normalization(
        _sim([_FAST_DRIVER, _SLOW_DRIVER]),
        "Canada Grand Prix",
        _gold("Canada Grand Prix", 78.0),
        current,
        is_wet_race=False,
    )

    window_median = current["LapTime_s"].median()
    expected_scale = 78.0 / window_median

    scales = (out["Sector1Time_s"] / 30.0).tolist()
    assert scales[0] == pytest.approx(expected_scale)
    assert scales[1] == pytest.approx(expected_scale)
    assert out["Sector3Time_s"].iloc[0] == pytest.approx(29.0 * expected_scale)


def test_driver_with_no_laps_falls_back_to_the_field_delta() -> None:
    """An unknown driver is neither flattered nor buried."""
    out = _apply_track_pace_normalization(
        _sim([_FAST_DRIVER, _SLOW_DRIVER, "GHOST"]),
        "Canada Grand Prix",
        _gold("Canada Grand Prix", 78.0),
        _current_laps(),
        is_wet_race=False,
    ).set_index("Driver")

    # median of the two known deltas (0.0, 0.25)
    assert out.loc["GHOST", "roll_laptime_3"] == pytest.approx(78.125)


def test_missing_historical_laps_fall_back_to_the_window_median() -> None:
    """An unknown target circuit lands the field on the window's level."""
    out = _apply_track_pace_normalization(
        _sim([_FAST_DRIVER]),
        "Never Raced Grand Prix",
        _gold("Some Other Grand Prix", 78.0),
        _current_laps(),
        is_wet_race=False,
    )

    assert out["roll_laptime_3"].iloc[0] == pytest.approx(81.0)


def test_wet_and_dry_laps_are_measured_separately() -> None:
    """The weather split applies to the driver deltas, not just the baseline."""
    current = _laps(
        [(_FAST_DRIVER, 1, 90.0, True)] * 2
        + [(_SLOW_DRIVER, 1, 91.0, True)] * 2
        + [(_FAST_DRIVER, 2, 100.0, True)] * 2
        + [(_SLOW_DRIVER, 2, 100.0, True)] * 2
        + [(_FAST_DRIVER, 1, 80.0, False)] * 2
        + [(_SLOW_DRIVER, 1, 99.0, False)] * 2
        + [(_FAST_DRIVER, 2, 100.0, False)] * 2
        + [(_SLOW_DRIVER, 2, 100.0, False)] * 2
    )

    wet = _driver_track_normalized_deltas(current, is_wet_race=True)
    dry = _driver_track_normalized_deltas(current, is_wet_race=False)

    assert wet[_FAST_DRIVER] == pytest.approx(-0.25)
    assert wet[_SLOW_DRIVER] == pytest.approx(0.25)
    assert dry[_FAST_DRIVER] == pytest.approx(-4.75)


def test_empty_window_is_a_graceful_no_op() -> None:
    """No usable laps means no delta — not an exception."""
    current = _laps([(_FAST_DRIVER, 1, float("nan"), False)])
    sim = _sim([_FAST_DRIVER, _SLOW_DRIVER])

    deltas = _driver_track_normalized_deltas(current, is_wet_race=False)
    assert deltas.empty

    out = _apply_track_pace_normalization(
        sim, "Canada Grand Prix", _gold("Canada Grand Prix", 78.0), current
    )
    assert out["roll_laptime_3"].tolist() == [78.0, 78.0]
    # season_global_median is NaN here, so the sector scale must be neutral.
    assert out["Sector1Time_s"].tolist() == [30.0, 30.0]


def _laps_with_sectors() -> pd.DataFrame:
    """Two circuits whose sectors and speeds differ, with clean per-round deltas.

    Round 1 sectors run ~25s and round 2 ~32s. Per round the fast driver is 0.2s up
    in round 1 and 0.3s up in round 2, so their measured delta is -0.25s; on speed
    they are +2 and +1 km/h, so +1.5 km/h. A *pooled* median over both circuits is
    dominated instead by how many laps each driver has at each.
    """
    rows: list[dict[str, object]] = []
    for _ in range(4):
        rows.append(
            {
                "Driver": _FAST_DRIVER,
                "RoundNumber": 1,
                "LapTime_s": 80.0,
                "Rainfall": False,
                "Sector1Time_s": 25.0,
                "SpeedI1": 200.0,
            }
        )
        rows.append(
            {
                "Driver": _SLOW_DRIVER,
                "RoundNumber": 1,
                "LapTime_s": 81.0,
                "Rainfall": False,
                "Sector1Time_s": 25.4,
                "SpeedI1": 196.0,
            }
        )
        rows.append(
            {
                "Driver": _FAST_DRIVER,
                "RoundNumber": 2,
                "LapTime_s": 100.5,
                "Rainfall": False,
                "Sector1Time_s": 32.0,
                "SpeedI1": 240.0,
            }
        )
        rows.append(
            {
                "Driver": _SLOW_DRIVER,
                "RoundNumber": 2,
                "LapTime_s": 100.0,
                "Rainfall": False,
                "Sector1Time_s": 32.6,
                "SpeedI1": 238.0,
            }
        )
    return pd.DataFrame(rows)


def _sim_with_pooled_gap() -> pd.DataFrame:
    """A scenario whose pooled sector and speed medians are badly contaminated.

    The fast driver carries a 4s better *pooled* sector and 20 km/h more speed, which
    is what the window's lap mix produces -- not pace.
    """
    return pd.DataFrame(
        [
            {
                "Driver": _FAST_DRIVER,
                "roll_laptime_3": 90.0,
                "roll_laptime_5": 90.0,
                "Sector1Time_s": 30.0,
                "SpeedI1": 300.0,
            },
            {
                "Driver": _SLOW_DRIVER,
                "roll_laptime_3": 90.0,
                "roll_laptime_5": 90.0,
                "Sector1Time_s": 26.0,
                "SpeedI1": 280.0,
            },
        ]
    )


def test_sector_deviations_are_rebuilt_from_per_round_deltas() -> None:
    """A contaminated pooled sector gap is replaced by the measured one."""
    current = _laps_with_sectors()
    out = _apply_track_pace_normalization(
        _sim_with_pooled_gap(),
        "Canada Grand Prix",
        _gold("Canada Grand Prix", 78.0),
        current,
        is_wet_race=False,
    ).set_index("Driver")

    scale = 78.0 / current["LapTime_s"].median()
    field_level = 28.0 * scale  # mean of the pooled 30.0 and 26.0, rescaled

    assert out.loc[_FAST_DRIVER, "Sector1Time_s"] == pytest.approx(
        field_level - 0.25 * scale
    )
    assert out.loc[_SLOW_DRIVER, "Sector1Time_s"] == pytest.approx(
        field_level + 0.25 * scale
    )

    # The published gap is the measured 0.5s, not the pooled 4s the window implied.
    gap = out["Sector1Time_s"].max() - out["Sector1Time_s"].min()
    assert gap == pytest.approx(0.5 * scale)
    assert gap < 1.0


def test_speed_deviations_are_rebuilt_but_not_rescaled() -> None:
    """Speeds are not proportional to lap time, so only their deltas are replaced."""
    out = _apply_track_pace_normalization(
        _sim_with_pooled_gap(),
        "Canada Grand Prix",
        _gold("Canada Grand Prix", 78.0),
        _laps_with_sectors(),
        is_wet_race=False,
    ).set_index("Driver")

    assert out.loc[_FAST_DRIVER, "SpeedI1"] == pytest.approx(291.5)
    assert out.loc[_SLOW_DRIVER, "SpeedI1"] == pytest.approx(288.5)
    # 3 km/h apart, not the pooled 20 the window implied.
    assert out["SpeedI1"].max() - out["SpeedI1"].min() == pytest.approx(3.0)


def test_driver_without_sector_laps_gets_the_bare_field_level() -> None:
    """An unknown driver is never handed another driver's deviation."""
    sim = pd.concat(
        [
            _sim_with_pooled_gap(),
            pd.DataFrame(
                [
                    {
                        "Driver": "GHOST",
                        "roll_laptime_3": 90.0,
                        "roll_laptime_5": 90.0,
                        "Sector1Time_s": 30.0,
                        "SpeedI1": 300.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    current = _laps_with_sectors()
    out = _apply_track_pace_normalization(
        sim,
        "Canada Grand Prix",
        _gold("Canada Grand Prix", 78.0),
        current,
        is_wet_race=False,
    ).set_index("Driver")

    scale = 78.0 / current["LapTime_s"].median()
    assert out.loc["GHOST", "Sector1Time_s"] == pytest.approx(
        float(sim["Sector1Time_s"].mean()) * scale
    )
    assert out.loc["GHOST", "SpeedI1"] == pytest.approx(float(sim["SpeedI1"].mean()))


def test_dispersion_check_passes_a_spread_the_laps_support(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 1.00x spread -- the corrected round -- raises nothing."""
    with caplog.at_level(logging.WARNING):
        ratio = check_published_dispersion(4.920, 4.897)

    assert ratio == pytest.approx(1.005, abs=0.001)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_dispersion_check_flags_the_regression_it_was_written_for(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The published 6.465s against a measured 4.897s must not pass silently."""
    with caplog.at_level(logging.WARNING):
        ratio = check_published_dispersion(6.465, 4.897)

    assert ratio == pytest.approx(1.32, abs=0.01)
    assert any("track mix" in record.getMessage() for record in caplog.records)


def test_dispersion_check_degrades_when_nothing_was_measured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No laps means no measurement, which is reported rather than assumed."""
    with caplog.at_level(logging.WARNING):
        ratio = check_published_dispersion(6.0, float("nan"))

    assert math.isnan(ratio)
    assert any("skipped" in record.getMessage() for record in caplog.records)


_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "outputs" / "laps"
_lap_files = sorted(_DATA_DIR.glob("season=*/**/*.parquet"))
_lap_files_2026 = sorted(_DATA_DIR.glob("season=2026/**/*.parquet"))


@pytest.mark.skipif(not _lap_files, reason="local lap data not ingested")
def test_real_window_shows_the_artefact_the_fix_removes() -> None:
    """Guard the fix against the data that produced the 13s spread."""
    current = pd.concat([pd.read_parquet(path) for path in _lap_files])

    pooled = current.groupby("Driver")["LapTime_s"].median()
    deltas = _driver_track_normalized_deltas(current, is_wet_race=False)

    assert pooled.max() - pooled.min() > 10.0
    assert deltas.max() - deltas.min() < (pooled.max() - pooled.min()) / 2


@pytest.mark.skipif(not _lap_files_2026, reason="local lap data not ingested")
def test_real_window_sectors_are_mostly_track_mix() -> None:
    """Pin the measurement that justifies rebuilding the sector deviations.

    Across the current-season window the pooled sector spread is 12-16x the
    per-circuit spread, so a model reading the pooled values is mostly reading which
    circuits each driver has laps at. If the data ever stops showing that, the
    normalisation should be re-derived rather than kept on faith.
    """
    current = pd.concat([pd.read_parquet(path) for path in _lap_files_2026])

    for column in ("Sector1Time_s", "Sector2Time_s", "Sector3Time_s"):
        pooled = current.groupby("Driver")[column].median()
        measured = _driver_track_normalized_deltas(
            current, is_wet_race=False, value_column=column
        )
        pooled_spread = pooled.max() - pooled.min()
        measured_spread = measured.max() - measured.min()

        assert measured_spread < pooled_spread / 4


# ── The served lap must state its traffic situation ──────────────────────────


def _driver_stats() -> pd.DataFrame:
    """Two drivers holding the columns the scenario builder reads."""
    return pd.DataFrame(
        [
            {
                "Driver": "VER",
                "Team": "Red Bull",
                "SpeedI1": 300.0,
                "SpeedI2": 250.0,
                "SpeedFL": 310.0,
                "SpeedST": 280.0,
                "Sector1Time_s": 30.0,
                "Sector2Time_s": 35.0,
                "Sector3Time_s": 25.0,
                "LapTime_s": 90.0,
                "roll_std_3": 0.2,
                "delta_roll_pace": -0.1,
                "tyre_deg_slope": 0.05,
                "tyre_life_norm": 0.5,
                "DriverPointsPreRace": 250,
                "TeamPointsPreRace": 400,
            },
            {
                "Driver": "HAM",
                "Team": "Ferrari",
                "SpeedI1": 299.0,
                "SpeedI2": 249.0,
                "SpeedFL": 309.0,
                "SpeedST": 279.0,
                "Sector1Time_s": 30.1,
                "Sector2Time_s": 35.1,
                "Sector3Time_s": 25.1,
                "LapTime_s": 90.2,
                "roll_std_3": 0.3,
                "delta_roll_pace": -0.05,
                "tyre_deg_slope": 0.06,
                "tyre_life_norm": 0.5,
                "DriverPointsPreRace": 240,
                "TeamPointsPreRace": 400,
            },
        ]
    )


def test_current_form_stats_collapses_laps_to_one_row_per_driver() -> None:
    """Current form is one observation per driver, medians over their laps."""
    laps = pd.DataFrame(
        [
            {
                "Driver": driver,
                "Team": "Red Bull" if driver == "VER" else "Ferrari",
                "LapTime_s": time,
                "SpeedI1": 300.0,
                "SpeedI2": 250.0,
                "SpeedFL": 310.0,
                "SpeedST": 280.0,
                "Sector1Time_s": 30.0,
                "Sector2Time_s": 35.0,
                "Sector3Time_s": 25.0,
                "roll_std_3": 0.2,
                "delta_roll_pace": -0.1,
                "tyre_deg_slope": 0.05,
                "tyre_life_norm": 0.5,
                "DriverPointsPreRace": 100,
                "TeamPointsPreRace": 200,
            }
            for driver, time in (("VER", 90.0), ("VER", 92.0), ("HAM", 91.0))
        ]
    )

    stats = _current_form_stats(laps)

    assert sorted(stats["Driver"]) == ["HAM", "VER"]
    assert stats.loc[stats["Driver"] == "VER", "LapTime_s"].iloc[0] == pytest.approx(
        91.0
    )
    assert stats.loc[stats["Driver"] == "VER", "Team"].iloc[0] == "Red Bull"


def test_simulation_scenario_serves_the_clean_air_case() -> None:
    """The unraced lap has to say it is a clean-air lap.

    The model is trained on measured exposure labels, so a served row that omits
    them would fall through to the trees' missing-value branch: the scenario has
    to state where in the field it is driven.
    """
    scenario = _build_simulation_scenario(
        _driver_stats(), 2026, 19, "Mexico City Grand Prix", 15
    )

    assert len(scenario) == 2
    for column, value in CLEAN_AIR_SCENARIO.items():
        assert (scenario[column] == value).all()
    assert (scenario["traffic_nearest_s"] <= scenario["traffic_ahead_s"]).all()


def test_served_feature_matrix_matches_the_trained_one() -> None:
    """Whichever label columns training sees, serving must see the same set."""
    scenario = _build_simulation_scenario(
        _driver_stats(), 2026, 19, "Mexico City Grand Prix", 15
    )

    x, _ = prepare_feature_matrix(scenario, require_target=False)

    assert {"traffic_ahead_s", "traffic_nearest_s"}.issubset(x.columns)
    assert "in_clean_air" not in x.columns


def test_gold_files_before_round_excludes_the_target_and_later(
    tmp_path: Path,
) -> None:
    """A backtest must not read the round it is predicting."""
    for season, rnd in ((2026, 1), (2026, 2), (2026, 3), (2025, 1)):
        directory = tmp_path / f"season={season}" / f"round={rnd:02d}"
        directory.mkdir(parents=True)
        (directory / "race_laps.parquet").write_bytes(b"")

    files = _gold_files_before_round(tmp_path, 2026, 3)

    assert [path.parent.name for path in files] == ["round=01", "round=02"]
