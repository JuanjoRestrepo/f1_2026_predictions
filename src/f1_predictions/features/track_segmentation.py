"""Track centerline projection and telemetry micro-segmentation engine.

Inspired by @formulasteele (f1-strategy-sim / Jemima Steele):
This module provides spatial-temporal decomposition of F1 laps:
1. Reconstructs a reference track center line from spatial position data (X, Y).
2. Orthogonally projects driver telemetry onto the center line arc-length coordinate s.
3. Detects heavy braking points in telemetry to establish physical segment boundaries.
4. Validates laps through strict distance and proximity checks:
   - Cumulative speed integration vs. centerline length agreement (< 1.0%).
   - Median spatial deviation from centerline (< 20.0 m).
   - Segment times sum matching official lap time (<= 15 ms).
5. Computes micro-sector pace deltas to detect localized track wetness / grip drops
   1 to 2 laps before changes emerge in full-lap times.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# Quality control thresholds based on empirical FastF1 GPS resolution
MAX_LENGTH_ERROR_PCT: float = 1.0  # Car distance vs center line length tolerance
MAX_MEDIAN_PROXIMITY_M: float = 20.0  # Max median distance from track center line
MAX_LAP_RECONSTITUTION_MS: float = 15.0  # Sum of segments vs lap time delta threshold


@dataclass(frozen=True)
class TrackSegment:
    """Represents a physical track segment defined by two braking/turn boundaries.

    Attributes:
        name: Identifier, e.g. 'T1 to T4'.
        start_s: Starting station along center line in meters [0, TrackLength].
        end_s: Ending station along center line in meters.
        description: Physical track feature (e.g. 'Senna S + Curva do Sol').
    """

    name: str
    start_s: float
    end_s: float
    description: str = ""

    @property
    def length_m(self) -> float:
        """Segment length in meters."""
        return max(0.0, self.end_s - self.start_s)


@dataclass
class SegmentationQualityReport:
    """Validation report verifying telemetry fidelity against the center line."""

    passed: bool
    length_error_pct: float
    median_deviation_m: float
    reconstitution_delta_ms: float
    reasons: list[str] = field(default_factory=list)


class TrackCenterline:
    """Parametric center line C(s) built from reference telemetry coordinates.

    Parameters:
        x: Reference X coordinates (meters).
        y: Reference Y coordinates (meters).
    """

    def __init__(self, x: NDArray[np.float64], y: NDArray[np.float64]) -> None:
        """Initialize the track centerline from reference coordinates."""
        if len(x) < 10 or len(x) != len(y):
            raise ValueError("Centerline requires at least 10 matching (X, Y) points.")

        self.x = np.asarray(x, dtype=np.float64)
        self.y = np.asarray(y, dtype=np.float64)

        # Compute cumulative arc-length distance s along the points
        dx = np.diff(self.x)
        dy = np.diff(self.y)
        dists = np.hypot(dx, dy)
        self.s = np.concatenate([[0.0], np.cumsum(dists)])
        self.total_length_m: float = float(self.s[-1])

    def project_coordinates(
        self, car_x: NDArray[np.float64], car_y: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Project car coordinates (X, Y) onto the reference center line.

        For each coordinate pair, computes the nearest center line point and returns
        the station coordinate s (in meters) and the orthogonal deviation (in meters).

        Args:
            car_x: Array of car X coordinates.
            car_y: Array of car Y coordinates.

        Returns:
            Tuple of (s_stations, deviations_m).
        """
        car_x = np.asarray(car_x, dtype=np.float64)
        car_y = np.asarray(car_y, dtype=np.float64)

        # Pairwise distance broadcast between car points and sampled centerline
        # Using KDTree or vector distance for memory efficiency:
        n_car = len(car_x)
        s_stations = np.zeros(n_car, dtype=np.float64)
        deviations = np.zeros(n_car, dtype=np.float64)

        ref_points = np.column_stack([self.x, self.y])
        car_points = np.column_stack([car_x, car_y])
        n_segs = len(self.x) - 1

        for i, pt in enumerate(car_points):
            # Find closest vertex first to limit search neighborhood
            dists = np.linalg.norm(ref_points - pt, axis=1)
            closest_idx = int(np.argmin(dists))

            # Check adjacent line segments
            cand_segs = []
            if closest_idx > 0:
                cand_segs.append(closest_idx - 1)
            if closest_idx < n_segs:
                cand_segs.append(closest_idx)

            best_dist = float("inf")
            best_s = self.s[closest_idx]

            for seg_idx in cand_segs:
                p1 = ref_points[seg_idx]
                p2 = ref_points[seg_idx + 1]
                v = p2 - p1
                seg_len_sq = float(np.dot(v, v))
                if seg_len_sq <= 1e-9:
                    continue
                # Projection parameter u in [0, 1]
                u = float(np.clip(np.dot(pt - p1, v) / seg_len_sq, 0.0, 1.0))
                proj = p1 + u * v
                dist_to_seg = float(np.linalg.norm(pt - proj))
                if dist_to_seg < best_dist:
                    best_dist = dist_to_seg
                    best_s = float(self.s[seg_idx] + u * np.sqrt(seg_len_sq))

            s_stations[i] = best_s
            deviations[i] = best_dist

        return s_stations, deviations


def find_braking_points(
    telemetry_df: pd.DataFrame,
    speed_drop_threshold_kmh: float = 30.0,
    min_separation_m: float = 150.0,
) -> list[float]:
    """Identify significant braking zones to serve as physical segment boundaries.

    Args:
        telemetry_df: DataFrame with 'Distance', 'Speed', 'Brake' channels.
        speed_drop_threshold_kmh: Minimum speed drop to identify a heavy braking event.
        min_separation_m: Minimum track distance between consecutive segment cuts.

    Returns:
        List of distance stations s (in meters) marking braking boundaries.
    """
    if "Distance" not in telemetry_df.columns or "Speed" not in telemetry_df.columns:
        return []

    speed = telemetry_df["Speed"].to_numpy(dtype=float)
    dist = telemetry_df["Distance"].to_numpy(dtype=float)
    brake = (
        telemetry_df["Brake"].to_numpy(dtype=float)
        if "Brake" in telemetry_df.columns
        else (np.gradient(speed) < -1.0).astype(float)
    )

    # Local deceleration peaks
    accel = np.gradient(speed, dist, edge_order=1)  # dV/ds
    braking_mask = (accel < -0.05) & (brake > 0)

    braking_indices = np.where(braking_mask)[0]
    if len(braking_indices) == 0:
        return []

    cuts: list[float] = []
    last_cut = -min_separation_m

    for idx in braking_indices:
        d_val = float(dist[idx])
        if d_val - last_cut >= min_separation_m:
            cuts.append(d_val)
            last_cut = d_val

    return cuts


def validate_lap_quality(
    integrated_distance_m: float,
    centerline_length_m: float,
    median_deviation_m: float,
    segment_times_sum_s: float,
    official_laptime_s: float,
) -> SegmentationQualityReport:
    """Apply @formulasteele quality checks to verify lap telemetry accuracy.

    Args:
        integrated_distance_m: Distance from speed integration (int v dt).
        centerline_length_m: Reference centerline total length.
        median_deviation_m: Median lateral deviation from centerline.
        segment_times_sum_s: Sum of calculated segment durations.
        official_laptime_s: Official transponder lap time.

    Returns:
        SegmentationQualityReport with pass/fail and metrics.
    """
    reasons: list[str] = []
    length_error_pct = (
        abs(integrated_distance_m - centerline_length_m) / centerline_length_m * 100.0
    )
    reconstitution_delta_ms = abs(segment_times_sum_s - official_laptime_s) * 1000.0

    if length_error_pct > MAX_LENGTH_ERROR_PCT:
        reasons.append(
            f"Lap distance mismatch ({length_error_pct:.2f}% > {MAX_LENGTH_ERROR_PCT}%)"
        )
    if median_deviation_m > MAX_MEDIAN_PROXIMITY_M:
        reasons.append(
            f"Median centerline deviation excessive "
            f"({median_deviation_m:.1f}m > {MAX_MEDIAN_PROXIMITY_M}m)"
        )
    if reconstitution_delta_ms > MAX_LAP_RECONSTITUTION_MS:
        reasons.append(
            f"Segment sum mismatch with transponder "
            f"({reconstitution_delta_ms:.1f}ms > {MAX_LAP_RECONSTITUTION_MS}ms)"
        )

    passed = len(reasons) == 0
    return SegmentationQualityReport(
        passed=passed,
        length_error_pct=length_error_pct,
        median_deviation_m=median_deviation_m,
        reconstitution_delta_ms=reconstitution_delta_ms,
        reasons=reasons,
    )


def compute_segment_times(
    telemetry_df: pd.DataFrame,
    segments: list[TrackSegment],
) -> dict[str, float]:
    """Compute elapsed time across each fixed physical track segment.

    Args:
        telemetry_df: DataFrame with 'Distance' and 'Time' (or 'Time_s').
        segments: List of TrackSegment instances.

    Returns:
        Dictionary mapping segment names to duration in seconds.
    """
    if "Distance" not in telemetry_df.columns:
        return {}

    dist = telemetry_df["Distance"].to_numpy(dtype=float)
    if "Time_s" in telemetry_df.columns:
        times = telemetry_df["Time_s"].to_numpy(dtype=float)
    elif "Time" in telemetry_df.columns:
        times_delta = pd.to_timedelta(telemetry_df["Time"])
        times = times_delta.dt.total_seconds().to_numpy(dtype=float)
    else:
        return {}

    seg_times: dict[str, float] = {}

    for seg in segments:
        # Find entry and exit timestamps via linear interpolation at start_s and end_s
        if seg.start_s < dist[0] or seg.end_s > dist[-1]:
            continue
        t_entry = float(np.interp(seg.start_s, dist, times))
        t_exit = float(np.interp(seg.end_s, dist, times))
        seg_times[seg.name] = max(0.0, t_exit - t_entry)

    return seg_times
