"""Traffic exposure labels for the f1_predictions feature engineering stage.

Rationale:
    A race lap is only comparable to another race lap when both were driven in
    comparable air. A car sitting one second behind another loses several tenths
    to dirty air and to lifting, so a driver's raw lap-time median mixes *pace*
    with *traffic situation*. Measured on this repository's own race laps, the
    median penalty decays monotonically with the gap to the car ahead
    (+0.57 s under 0.5 s, +0.29 s at 0.5-1.0 s, +0.09 s at 1.0-1.5 s, ~0 s
    beyond 1.5 s when tyre age is held constant within the stint).

    The labels computed here let the model separate the two effects instead of
    fitting a compromise between them, and let downstream analysis restrict a
    pace measurement to laps that were actually driven in clean air.

Method:
    FastF1's per-lap ``LapStartTime`` and ``Time`` give each lap a known
    on-track interval. Sampling each lap at fixed fractions of its duration and
    mapping every other car's active lap to a track position in laps
    (``LapNumber - 1 + fraction_complete``) yields an estimate of how far ahead
    the nearest car is, expressed in seconds of track distance.

    The conversion from lap fraction to seconds uses the session's own median
    lap time, because one lap of track distance is worth 70 s at Monza and
    120 s at Singapore. A single global constant would mis-scale every gap by
    up to 30% across the calendar.

Scope:
    Interval positions are session-relative, so the computation is only
    meaningful within one session: :func:`add_traffic_exposure` refuses inputs
    that mix events. Pit laps, safety-car laps and red-flag stoppages are
    already removed upstream in the Silver layer, which is what makes the
    on-track intervals trustworthy in the first place.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# In-lap sample points, as a fraction of each lap's duration. Four samples keep
# the estimate insensitive to where in the lap the focus car actually was, at a
# cost of four position lookups per lap.
TRAFFIC_SAMPLE_FRACTIONS: tuple[float, ...] = (0.20, 0.40, 0.60, 0.80)

# A lap counts as clean when no car was within this many seconds ahead of it and
# no car was within the nearer threshold in either direction. 2.0 s ahead is
# where the measured dirty-air penalty has decayed to its noise floor.
CLEAN_AIR_AHEAD_S: float = 2.0
CLEAN_AIR_NEAREST_S: float = 1.2

# On-track interval sanity window. A lap whose interval falls outside this range
# is an in-lap, an out-lap or a stoppage the cleaning stage did not remove, and
# its position estimate would poison every other car's margin.
MIN_LAP_DURATION_S: float = 60.0
MAX_LAP_DURATION_S: float = 180.0

# Label columns appended to the Gold-layer frame. All three are numeric so they
# satisfy the Gold contract and can be consumed by the GBMs directly.
TRAFFIC_COLUMNS: tuple[str, ...] = (
    "traffic_ahead_s",
    "traffic_nearest_s",
    "in_clean_air",
)

# Scenario values used when serving an unraced round. The simulated lap is by
# definition a clean-air lap, so the model is asked for pace with no car
# influence. The values are the measured medians of clean-air laps in this
# dataset (2022-2026: ahead 4.95 s, nearest 2.98 s), which keeps the served row
# at the centre of the clean-air region it was trained on instead of at an
# extrapolated extreme. Nearest stays below ahead, as it must: a nearest-car
# distance is a minimum over both directions while a gap-to-ahead is not.
CLEAN_AIR_SCENARIO_AHEAD_S: float = 5.0
CLEAN_AIR_SCENARIO_NEAREST_S: float = 3.0
CLEAN_AIR_SCENARIO: dict[str, float] = {
    "traffic_ahead_s": CLEAN_AIR_SCENARIO_AHEAD_S,
    "traffic_nearest_s": CLEAN_AIR_SCENARIO_NEAREST_S,
    "in_clean_air": 1.0,
}

_NO_INTERVAL = np.inf


# ── Public API ────────────────────────────────────────────────────────────────


def add_traffic_exposure(
    laps: pd.DataFrame,
    *,
    driver_col: str = "Driver",
    lap_col: str = "LapNumber",
    start_col: str = "LapStartTime",
    end_col: str = "Time",
    lap_time_col: str = "LapTime_s",
    sample_fractions: Sequence[float] = TRAFFIC_SAMPLE_FRACTIONS,
    clean_ahead_s: float = CLEAN_AIR_AHEAD_S,
    clean_nearest_s: float = CLEAN_AIR_NEAREST_S,
    min_lap_duration_s: float = MIN_LAP_DURATION_S,
    max_lap_duration_s: float = MAX_LAP_DURATION_S,
) -> pd.DataFrame:
    """Append per-lap traffic exposure labels for a single session.

    Args:
        laps: One session's clean laps. Must contain ``driver_col``,
            ``lap_col``, ``start_col``, ``end_col`` and ``lap_time_col``.
            ``start_col``/``end_col`` are session-relative offsets, either
            timedeltas (Silver/Gold layer) or already in seconds.
        driver_col: Column holding the driver identifier.
        lap_col: Column holding the lap number (1-indexed per driver).
        start_col: Column holding each lap's on-track start offset.
        end_col: Column holding each lap's on-track end offset.
        lap_time_col: Column holding each lap's duration in seconds, used to
            scale a lap of track distance into seconds.
        sample_fractions: In-lap sample points as fractions of lap duration.
        clean_ahead_s: Minimum gap to the car ahead for a clean lap.
        clean_nearest_s: Minimum distance to any car for a clean lap.
        min_lap_duration_s: Shortest interval treated as a racing lap.
        max_lap_duration_s: Longest interval treated as a racing lap.

    Returns:
        A new DataFrame with rows and order preserved, plus:

        - ``traffic_ahead_s``: seconds of track distance to the nearest car
          ahead, minimum across sample points. ``NaN`` when the lap has no
          usable interval.
        - ``traffic_nearest_s``: seconds of track distance to the nearest car
          in either direction.
        - ``in_clean_air``: ``1.0`` when the lap clears both thresholds,
          ``0.0`` when it does not, ``NaN`` when the margins are unknown.

    Raises:
        TypeError: If ``laps`` is not a pandas DataFrame.
        KeyError: If a required column is absent.
        ValueError: If the frame mixes events.

    Note:
        Laps whose offsets, lap number or duration cannot support a position
        estimate are excluded from the interval set and returned with NaN
        labels. Excluding them silently is not an option — an unusable interval
        would corrupt every other car's margin — so the count is logged.

    Example::

        from f1_predictions.features.traffic_exposure import add_traffic_exposure

        labelled = add_traffic_exposure(clean_laps)
        labelled[["Driver", "LapNumber", "traffic_ahead_s", "in_clean_air"]].head()
    """
    if not isinstance(laps, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(laps).__name__}"
        raise TypeError(msg)

    _assert_single_event(laps)
    _assert_columns_present(
        laps, [driver_col, lap_col, start_col, end_col, lap_time_col]
    )

    result = laps.copy()
    starts = _to_seconds(laps[start_col]).to_numpy(dtype=float)
    ends = _to_seconds(laps[end_col]).to_numpy(dtype=float)
    lap_numbers = pd.to_numeric(laps[lap_col], errors="coerce").to_numpy(dtype=float)
    durations = ends - starts

    valid = (
        np.isfinite(durations)
        & (durations >= min_lap_duration_s)
        & (durations <= max_lap_duration_s)
        & np.isfinite(lap_numbers)
        & np.isfinite(starts)
        & np.isfinite(ends)
    )
    _warn_unusable(laps, valid, durations, lap_numbers)
    reference_lap_s = _reference_lap_seconds(laps[lap_time_col], durations, valid)

    if not np.isfinite(reference_lap_s) or int(valid.sum()) < 2:
        logger.warning(
            "Traffic exposure not computable: %d usable laps and reference lap "
            "%.3f s. Writing %s as NaN.",
            int(valid.sum()),
            reference_lap_s,
            list(TRAFFIC_COLUMNS),
        )
        return _with_empty_labels(result)

    groups = _driver_groups(laps, driver_col, valid)
    ahead, nearest = _lap_traffic_margins(
        starts=starts[valid],
        ends=ends[valid],
        lap_numbers=lap_numbers[valid],
        driver_groups=groups,
        reference_lap_s=float(reference_lap_s),
        sample_fractions=sample_fractions,
    )

    ahead_full = np.full(len(result), np.nan, dtype=float)
    nearest_full = np.full(len(result), np.nan, dtype=float)
    ahead_full[valid] = _finite_or_nan(ahead)
    nearest_full[valid] = _finite_or_nan(nearest)

    result["traffic_ahead_s"] = ahead_full
    result["traffic_nearest_s"] = nearest_full
    result["in_clean_air"] = np.where(
        np.isnan(ahead_full) | np.isnan(nearest_full),
        np.nan,
        ((ahead_full >= clean_ahead_s) & (nearest_full >= clean_nearest_s)).astype(
            float
        ),
    )

    known = np.isfinite(result["traffic_ahead_s"].to_numpy(dtype=float))
    if known.any():
        ahead_known = result["traffic_ahead_s"].to_numpy(dtype=float)[known]
        clean_share = float(np.nanmean(result["in_clean_air"].to_numpy(dtype=float)))
        median_ahead = float(np.median(ahead_known))
    else:
        clean_share = float("nan")
        median_ahead = float("nan")
    logger.info(
        "Traffic exposure added: reference lap %.2f s | %d/%d laps with usable "
        "intervals | %d empty | clean-air share %.1f%% | median gap to car "
        "ahead %.2f s",
        reference_lap_s,
        int(valid.sum()),
        len(result),
        int(len(result) - valid.sum()),
        clean_share * 100.0,
        median_ahead,
    )
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────


def _lap_traffic_margins(
    *,
    starts: NDArray[np.float64],
    ends: NDArray[np.float64],
    lap_numbers: NDArray[np.float64],
    driver_groups: Iterable[NDArray[np.int64]],
    reference_lap_s: float,
    sample_fractions: Sequence[float],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Estimate gap-to-car-ahead and nearest-car distance for each lap.

    Args:
        starts: On-track start offset per lap, in seconds.
        ends: On-track end offset per lap, in seconds.
        lap_numbers: Lap number per row, 1-indexed per driver.
        driver_groups: Row positions belonging to each driver.
        reference_lap_s: Seconds one lap of track distance is worth.
        sample_fractions: In-lap sample points as fractions of lap duration.

    Returns:
        ``(ahead, nearest)`` in seconds, aligned with the input rows.
        ``inf`` marks a lap with no other car on track at any sample point.
    """
    n_rows = len(starts)
    ahead = np.full(n_rows, _NO_INTERVAL, dtype=float)
    nearest = np.full(n_rows, _NO_INTERVAL, dtype=float)
    durations = ends - starts

    for group in driver_groups:
        other = np.zeros(n_rows, dtype=bool)
        other[group] = True
        s = starts[group]
        e = ends[group]
        laps_of_other = lap_numbers[group]
        order = np.argsort(s, kind="stable")
        s, e, laps_of_other = s[order], e[order], laps_of_other[order]
        span = np.maximum(e - s, 1e-9)

        for fraction in sample_fractions:
            samples = starts + fraction * durations
            position = np.searchsorted(s, samples, side="right") - 1
            inside = position >= 0
            clipped = np.clip(position, 0, len(s) - 1)
            active = inside & (e[clipped] >= samples) & ~other

            progress_other = (laps_of_other[clipped] - 1.0) + (
                samples - s[clipped]
            ) / span[clipped]
            progress_focal = (lap_numbers - 1.0) + fraction
            forward = (progress_other - progress_focal) % 1.0

            ahead = np.minimum(ahead, np.where(active, forward, _NO_INTERVAL))
            nearest = np.minimum(
                nearest,
                np.where(active, np.minimum(forward, 1.0 - forward), _NO_INTERVAL),
            )

    return ahead * reference_lap_s, nearest * reference_lap_s


def _driver_groups(
    laps: pd.DataFrame, driver_col: str, valid: NDArray[np.bool_]
) -> list[NDArray[np.int64]]:
    """Row positions per driver, restricted to laps with a usable interval."""
    positions = np.arange(len(laps), dtype=np.int64)[valid]
    valid_laps = laps.loc[valid, [driver_col]]
    groups: list[NDArray[np.int64]] = []
    for _, index in valid_laps.groupby(driver_col, sort=False).indices.items():
        groups.append(positions[np.sort(np.asarray(index, dtype=np.int64))])
    return groups


def _reference_lap_seconds(
    lap_times: pd.Series, durations: NDArray[np.float64], valid: NDArray[np.bool_]
) -> float:
    """Session median lap time, falling back to the median usable duration."""
    times = pd.to_numeric(lap_times, errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(times)
    if finite.any():
        return float(np.median(times[finite]))
    usable = durations[valid & np.isfinite(durations)]
    if usable.size:
        return float(np.median(usable))
    return float("nan")


def _with_empty_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the label columns as NaN, preserving rows and order."""
    for column in TRAFFIC_COLUMNS:
        df[column] = np.nan
    return df


def _finite_or_nan(values: NDArray[np.float64]) -> NDArray[np.float64]:
    """Replace non-finite sentinels with NaN for the Gold-layer contract."""
    return np.where(np.isfinite(values), values, np.nan)


def _to_seconds(series: pd.Series) -> pd.Series:
    """Convert a timedelta or numeric offset column to float seconds."""
    if pd.api.types.is_timedelta64_dtype(series):
        return cast(pd.Series, series.dt.total_seconds())
    return pd.to_numeric(series, errors="coerce")


def _assert_single_event(laps: pd.DataFrame) -> None:
    """Reject frames mixing sessions, whose offsets are not comparable."""
    for column in ("EventName", "Season", "RoundNumber"):
        if column in laps.columns and laps[column].nunique(dropna=True) > 1:
            msg = (
                f"add_traffic_exposure expects a single session, but "
                f"'{column}' holds {laps[column].nunique(dropna=True)} values. "
                "Session-relative offsets are only comparable within one "
                "session; call this per round."
            )
            raise ValueError(msg)


def _assert_columns_present(df: pd.DataFrame, required: list[str]) -> None:
    """Raise KeyError if any required column is absent from df."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        msg = (
            f"[add_traffic_exposure] Required column(s) missing from DataFrame: "
            f"{missing}. Available: {list(df.columns)}"
        )
        raise KeyError(msg)


def _warn_unusable(
    laps: pd.DataFrame,
    valid: NDArray[np.bool_],
    durations: NDArray[np.float64],
    lap_numbers: NDArray[np.float64],
) -> None:
    """Log a breakdown of laps excluded from the on-track interval set.

    An unusable interval is not merely unlabelled: while it is missing, every
    other car's margin is computed against a partially occupied field. That is
    acceptable when it is rare and visible, which is what this warning provides.
    """
    excluded = ~valid
    if not excluded.any():
        return
    logger.warning(
        "Traffic exposure: %d/%d laps excluded from the on-track interval set "
        "(non-finite offsets=%d, non-finite lap number=%d, duration outside "
        "[%.0f, %.0f]s=%d). Their %s labels are NaN.",
        int(excluded.sum()),
        len(laps),
        int((~np.isfinite(durations)).sum()),
        int((~np.isfinite(lap_numbers)).sum()),
        MIN_LAP_DURATION_S,
        MAX_LAP_DURATION_S,
        int(
            (
                np.isfinite(durations)
                & ((durations < MIN_LAP_DURATION_S) | (durations > MAX_LAP_DURATION_S))
            ).sum()
        ),
        list(TRAFFIC_COLUMNS),
    )
