"""Unit tests for the TrackCenterline and micro-segmentation engine."""

import numpy as np
import pandas as pd
import pytest

from f1_predictions.features.track_segmentation import (
    TrackCenterline,
    TrackSegment,
    compute_segment_times,
    find_braking_points,
    validate_lap_quality,
)


def test_track_centerline_projection() -> None:
    """Test orthogonal projection of coordinates onto a reference centerline."""
    # Create a 200m circular/linear track segment
    t = np.linspace(0, 10, 50)
    x = t * 10.0
    y = np.zeros_like(x)

    centerline = TrackCenterline(x, y)
    assert np.isclose(centerline.total_length_m, 100.0)

    # Car coordinates shifted by 5m laterally
    car_x = np.array([0.0, 50.0, 100.0])
    car_y = np.array([5.0, 5.0, 5.0])

    s_stations, deviations = centerline.project_coordinates(car_x, car_y)

    assert np.allclose(s_stations, [0.0, 50.0, 100.0], atol=2.5)
    assert np.allclose(deviations, [5.0, 5.0, 5.0], atol=1e-3)


def test_track_centerline_rejects_insufficient_points() -> None:
    """Verify minimum coordinate count assertion."""
    with pytest.raises(ValueError, match="at least 10 matching"):
        TrackCenterline(np.array([1.0, 2.0]), np.array([1.0, 2.0]))


def test_find_braking_points() -> None:
    """Identify deceleration zones based on speed drops and brake actuation."""
    # Simulate a straight into a heavy braking turn
    dist = np.linspace(0, 1000, 100)
    # Speed is 300 km/h until 400m, drops to 100 km/h at 500m
    decel_speed = 300.0 - 2.0 * (dist - 400)
    speed = np.where(dist < 400, 300.0, np.where(dist < 500, decel_speed, 100.0))
    brake = np.where((dist >= 400) & (dist <= 500), 100.0, 0.0)

    df = pd.DataFrame({"Distance": dist, "Speed": speed, "Brake": brake})
    cuts = find_braking_points(df, min_separation_m=100.0)

    assert len(cuts) >= 1
    # First cut should be around 400m
    assert any(390 <= c <= 430 for c in cuts)


def test_validate_lap_quality_pass_and_fail() -> None:
    """Test validation reports based on @formulasteele quality checks."""
    # Passing lap
    report_pass = validate_lap_quality(
        integrated_distance_m=4309.0,
        centerline_length_m=4309.0,
        median_deviation_m=3.5,
        segment_times_sum_s=75.540,
        official_laptime_s=75.545,
    )
    assert report_pass.passed
    assert len(report_pass.reasons) == 0

    # Failing lap on distance length error (> 1%)
    report_fail = validate_lap_quality(
        integrated_distance_m=4500.0,
        centerline_length_m=4309.0,
        median_deviation_m=25.0,
        segment_times_sum_s=75.500,
        official_laptime_s=75.600,
    )
    assert not report_fail.passed
    assert len(report_fail.reasons) == 3


def test_compute_segment_times() -> None:
    """Verify segment timing interpolation."""
    dist = np.array([0.0, 100.0, 200.0, 300.0, 400.0])
    times_s = np.array([0.0, 5.0, 10.0, 15.0, 20.0])
    df = pd.DataFrame({"Distance": dist, "Time_s": times_s})

    segments = [
        TrackSegment(name="T1 to T4", start_s=0.0, end_s=200.0),
        TrackSegment(name="T4 to T6", start_s=200.0, end_s=400.0),
    ]

    res = compute_segment_times(df, segments)
    assert np.isclose(res["T1 to T4"], 10.0)
    assert np.isclose(res["T4 to T6"], 10.0)
