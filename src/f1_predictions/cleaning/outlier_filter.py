"""Lap outlier filtering for the f1_predictions cleaning stage.

Responsibilities:
    Remove laps that would skew the model's understanding of representative
    race pace. The four categories of invalid laps in F1 data are:

    1. **Out-laps**: The lap leaving the pit lane. Lap time includes the slow
       pit lane exit and is ~20-40% slower than a flying lap. Identified by
       a non-null ``PitOutTime_s`` (after Timedelta conversion).

    2. **In-laps**: The lap entering the pit lane. Lap time is artificially
       slow because the driver lifts before the pit entrance. Identified by
       a non-null ``PitInTime_s``.

    3. **Yellow flag / Safety Car laps**: Drivers are required to slow
       significantly under local yellows (TrackStatus="2") and must not
       overtake under Full Safety Car (TrackStatus="4") or VSC ("6").
       These laps do not represent the car's true performance envelope.

    4. **Statistical outliers**: Laps that are more than ``z_threshold``
       standard deviations above a driver's median lap time in a stint.
       This catches: slow laps after spins/off-track excursions, laps behind
       slow backmarkers, and sensor glitches that produce impossible times.
       We filter above the median only — unusually fast laps (push laps,
       late qualifying laps) are valid data and must NOT be removed.

Design decisions:
    - Each filter is a standalone function accepting and returning a DataFrame.
      They are composable: apply them in sequence via ``apply_all_filters()``.
    - ``apply_all_filters()`` logs a breakdown of rows removed per filter
      so the cleaning stage is fully auditable in the pipeline log.
    - All functions are pure (copy semantics) and idempotent.
    - The statistical outlier threshold (z=2.5) was calibrated on 2023-2024
      race data. Tighten to z=2.0 to be more aggressive; loosen to z=3.0
      to preserve more marginal laps. Document any change in CHANGELOG.md.

Track status codes (FIA):
    "1" = Track clear (green flag)
    "2" = Yellow flag (local)
    "4" = Safety Car
    "5" = Red Flag
    "6" = Virtual Safety Car (VSC)
    "7" = VSC ending
"""

import numpy as np
import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Track status values that indicate a neutralised or restricted period.
# Laps completed entirely under these statuses are not representative pace.
# "1" (clear) and "2" (local yellow beginning) have nuance:
#   - A lap started on a green flag but completed under local yellow is still
#     tainted. The full-lap filter on TrackStatus covers this conservatively.
NEUTRALISED_TRACK_STATUSES: frozenset[str] = frozenset({"2", "4", "5", "6", "7"})

# Z-score threshold for statistical outlier detection per driver per stint.
# Laps more than this many standard deviations above the driver's stint median
# are excluded. Applied above the median only (slow outliers), not below.
DEFAULT_Z_THRESHOLD: float = 2.5

# Minimum laps in a stint to apply z-score filtering. Below this threshold,
# there is insufficient data to compute a reliable z-score, so we skip it
# rather than risk removing valid data points.
MIN_LAPS_FOR_Z_FILTER: int = 4

# Minimum valid lap time in seconds. Laps shorter than this are physically
# impossible and indicate a telemetry error (e.g., lap counter reset).
# The shortest recorded F1 lap is ~55s (Monaco Q, short tracks).
MIN_LAP_TIME_SECONDS: float = 50.0

# Maximum valid lap time in seconds. Laps longer than this are likely Safety
# Car periods or undetected formation laps (cap at ~3x a typical fast lap).
MAX_LAP_TIME_SECONDS: float = 600.0


# ── Individual filters ────────────────────────────────────────────────────────


def filter_out_laps(
    df: pd.DataFrame, pit_out_col: str = "PitOutTime_s"
) -> pd.DataFrame:
    """Remove pit-exit (out) laps from the laps DataFrame.

    Out-laps are identified by a non-null ``PitOutTime_s`` value. These laps
    include the slow pit-lane exit and underrepresent race pace by 20-40%.

    Args:
        df: Cleaned laps DataFrame. Must contain ``pit_out_col``.
            If the column is absent, the DataFrame is returned unchanged
            with a warning (graceful degradation for qualifying sessions
            which have no pit-out information).
        pit_out_col: Column name for pit-exit time in seconds. The
            ``_s`` suffix indicates post-Timedelta-conversion.

    Returns:
        DataFrame with out-laps removed.
    """
    if pit_out_col not in df.columns:
        logger.warning(
            "Column '%s' not found — out-lap filter skipped. "
            "Expected after Timedelta conversion.",
            pit_out_col,
        )
        return df

    mask_out = df[pit_out_col].notna()
    n_removed = int(mask_out.sum())
    result = df[~mask_out].copy()
    logger.debug("Out-lap filter: removed %d laps (out-laps).", n_removed)
    return result


def filter_in_laps(df: pd.DataFrame, pit_in_col: str = "PitInTime_s") -> pd.DataFrame:
    """Remove pit-entry (in) laps from the laps DataFrame.

    In-laps are identified by a non-null ``PitInTime_s`` value. Drivers lift
    significantly before the pit entrance, making these laps unrepresentative.

    Args:
        df: Cleaned laps DataFrame.
        pit_in_col: Column name for pit-entry time in seconds.

    Returns:
        DataFrame with in-laps removed.
    """
    if pit_in_col not in df.columns:
        logger.warning("Column '%s' not found — in-lap filter skipped.", pit_in_col)
        return df

    mask_in = df[pit_in_col].notna()
    n_removed = int(mask_in.sum())
    result = df[~mask_in].copy()
    logger.debug("In-lap filter: removed %d laps (in-laps).", n_removed)
    return result


def filter_neutralised_laps(
    df: pd.DataFrame,
    track_status_col: str = "TrackStatus",
    neutralised_statuses: frozenset[str] = NEUTRALISED_TRACK_STATUSES,
) -> pd.DataFrame:
    """Remove laps completed under yellow flag, Safety Car, or VSC conditions.

    TrackStatus is a string code set by the FIA race control system. Any lap
    where the status is in ``neutralised_statuses`` is excluded because
    drivers cannot race at representative pace under these conditions.

    Args:
        df: Cleaned laps DataFrame.
        track_status_col: Column containing FIA track status codes.
        neutralised_statuses: Set of status codes to treat as neutralised.
            Defaults to ``NEUTRALISED_TRACK_STATUSES``.

    Returns:
        DataFrame with neutralised laps removed.
    """
    if track_status_col not in df.columns:
        logger.warning(
            "Column '%s' not found — neutralised lap filter skipped.",
            track_status_col,
        )
        return df

    mask_neutralised = df[track_status_col].isin(neutralised_statuses)
    n_removed = int(mask_neutralised.sum())
    result = df[~mask_neutralised].copy()
    logger.debug(
        "Neutralised lap filter: removed %d laps (statuses: %s).",
        n_removed,
        sorted(neutralised_statuses),
    )
    return result


def filter_impossible_lap_times(
    df: pd.DataFrame,
    lap_time_col: str = "LapTime_s",
    min_seconds: float = MIN_LAP_TIME_SECONDS,
    max_seconds: float = MAX_LAP_TIME_SECONDS,
) -> pd.DataFrame:
    """Remove laps with physically impossible lap times.

    Filters out laps below ``min_seconds`` (telemetry reset / sensor error)
    and above ``max_seconds`` (formation laps or undetected SC periods that
    slipped through the TrackStatus filter).

    Args:
        df: Laps DataFrame with ``LapTime_s`` in decimal seconds.
        lap_time_col: Column name for the lap time in seconds (post-conversion).
        min_seconds: Minimum plausible lap time. Default 50s.
        max_seconds: Maximum plausible lap time. Default 600s (10 minutes).

    Returns:
        DataFrame with impossible lap times removed. Rows where
        ``lap_time_col`` is NaN are also removed here — they cannot be
        used as training data and are handled separately in imputation.
    """
    if lap_time_col not in df.columns:
        logger.warning(
            "Column '%s' not found — impossible lap time filter skipped.", lap_time_col
        )
        return df

    initial_len = len(df)
    # Drop NaN first — comparison operators treat NaN as False, which would
    # silently retain NaN rows in the valid range.
    result = df.dropna(subset=[lap_time_col]).copy()
    n_nan = initial_len - len(result)

    mask_valid = result[lap_time_col].between(min_seconds, max_seconds)
    n_impossible = int((~mask_valid).sum())
    result = result[mask_valid].copy()

    logger.debug(
        "Impossible lap time filter: removed %d NaN + %d out-of-range laps "
        "(range: %.0f-%.0fs).",
        n_nan,
        n_impossible,
        min_seconds,
        max_seconds,
    )
    return result


def filter_statistical_outliers(
    df: pd.DataFrame,
    lap_time_col: str = "LapTime_s",
    group_cols: list[str] | None = None,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    min_laps: int = MIN_LAPS_FOR_Z_FILTER,
) -> pd.DataFrame:
    """Remove statistically slow laps using per-driver, per-stint z-scores.

    For each (Driver, Stint) group, computes the z-score of each lap time
    relative to the group median and MAD (Median Absolute Deviation).
    MAD is used instead of standard deviation because it is robust to the
    outliers we are trying to detect — a single very slow lap inflates std
    and would suppress the z-score of other slow laps.

    Only laps above the group median are considered for removal (z > 0).
    Faster-than-median laps (push laps, qualifying flyers) must be retained.

    Args:
        df: Laps DataFrame with converted lap time column.
        lap_time_col: Lap time column in decimal seconds.
        group_cols: Columns defining the grouping context.
            Defaults to ``["Driver", "Stint"]`` when ``None``.
        z_threshold: Modified z-score threshold above which a lap is
            considered an outlier. Default 2.5 (calibrated on 2023-2024 data).
        min_laps: Minimum group size to apply the filter. Groups smaller than
            this have the filter skipped (insufficient statistical power).

    Returns:
        DataFrame with statistical outlier laps removed.
    """
    if lap_time_col not in df.columns:
        logger.warning(
            "Column '%s' not found — statistical outlier filter skipped.", lap_time_col
        )
        return df

    groups = group_cols if group_cols is not None else ["Driver", "Stint"]
    missing_groups = [c for c in groups if c not in df.columns]
    if missing_groups:
        logger.warning(
            "Group column(s) %s not found — statistical outlier filter skipped.",
            missing_groups,
        )
        return df

    result = df.copy()
    outlier_mask = pd.Series(False, index=result.index)

    for group_key, group_df in result.groupby(groups, dropna=True):
        lap_times = group_df[lap_time_col].dropna()
        if len(lap_times) < min_laps:
            logger.debug(
                "Group %s has %d laps < min_laps=%d — skipping z-score filter.",
                group_key,
                len(lap_times),
                min_laps,
            )
            continue

        median = lap_times.median()
        # MAD: Median Absolute Deviation — robust scale estimator.
        # Multiplier 1.4826 scales MAD to be consistent with std for normal data.
        mad = float(np.median(np.abs(lap_times - median))) * 1.4826
        if mad == 0:
            # All laps identical (extremely rare); no outlier detection possible.
            continue

        modified_z = (group_df[lap_time_col] - median) / mad
        # Only flag laps that are slower than the median (z > 0)
        is_outlier = (modified_z > z_threshold) & group_df[lap_time_col].notna()
        outlier_mask.loc[group_df.index] = is_outlier

    n_outliers = int(outlier_mask.sum())
    result = result[~outlier_mask].copy()
    logger.debug(
        "Statistical outlier filter: removed %d laps (z_threshold=%.1f, groups=%s).",
        n_outliers,
        z_threshold,
        groups,
    )
    return result


# ── Composed pipeline ─────────────────────────────────────────────────────────


def apply_all_filters(
    df: pd.DataFrame,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
) -> tuple[pd.DataFrame, dict[str, int | float]]:
    """Apply the full outlier filter sequence and return removal statistics.

    Applies filters in order:
        1. Impossible lap times (NaN + out-of-range) — hard physical constraints.
        2. Out-laps — pit-exit laps.
        3. In-laps — pit-entry laps.
        4. Neutralised laps — yellow flag, SC, VSC.
        5. Statistical outliers — slow laps relative to driver stint pace.

    Order matters: the impossible lap time filter must run first to ensure NaN
    rows are removed before z-score statistics are computed (NaN propagation
    in median/MAD would produce incorrect results).

    Args:
        df: Raw laps DataFrame after Timedelta conversion and team normalization.
        z_threshold: Modified z-score threshold for step 5. See
            ``filter_statistical_outliers()`` for calibration guidance.

    Returns:
        A tuple of:
            - The filtered DataFrame.
            - A dict mapping filter name → number of rows removed at that step,
              plus ``"total_removed"`` and ``"retention_pct"``.

    Example::

        from f1_predictions.cleaning.outlier_filter import apply_all_filters

        filtered_laps, stats = apply_all_filters(clean_laps)
        logger.info("Filtering stats: %s", stats)
        # {"impossible": 3, "out_laps": 42, "in_laps": 41, ...}
    """
    initial_len = len(df)
    stats: dict[str, int | float] = {}

    df1 = filter_impossible_lap_times(df)
    stats["impossible"] = initial_len - len(df1)

    df2 = filter_out_laps(df1)
    stats["out_laps"] = len(df1) - len(df2)

    df3 = filter_in_laps(df2)
    stats["in_laps"] = len(df2) - len(df3)

    df4 = filter_neutralised_laps(df3)
    stats["neutralised"] = len(df3) - len(df4)

    df5 = filter_statistical_outliers(df4, z_threshold=z_threshold)
    stats["statistical_outliers"] = len(df4) - len(df5)

    total_removed = initial_len - len(df5)
    retention_pct = round(len(df5) / initial_len * 100, 2) if initial_len > 0 else 0.0
    stats["total_removed"] = total_removed
    stats["retention_pct"] = retention_pct

    logger.info(
        "Outlier filtering complete: %d → %d laps retained (%.1f%%). Breakdown: %s",
        initial_len,
        len(df5),
        retention_pct,
        {k: v for k, v in stats.items() if k not in ("total_removed", "retention_pct")},
    )
    return df5, stats
