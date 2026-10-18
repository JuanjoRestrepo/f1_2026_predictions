"""Rolling pace window features for the f1_predictions feature engineering stage.

Rationale:
    A driver's single-lap time is noisy — it reflects traffic, micro-errors,
    and tyre warm-up transients. The rolling mean of the last N clean laps
    within a stint captures the driver's *representative pace* at a given
    point in the race, which is the signal the model needs to rank finishing
    order.

    Two window sizes are computed:
        - ``roll_laptime_3``  : 3-lap rolling mean — captures very recent pace.
        - ``roll_laptime_5``  : 5-lap rolling mean — smooths more noise.
        - ``roll_std_3``      : 3-lap rolling std — captures pace consistency.

    All rolling computations are scoped per (Driver, Stint) using
    ``groupby + transform``. Rolling across stint boundaries would conflate
    different tyre and fuel conditions, introducing spurious correlations.

Causal (pre-lap, t-1) boundary — Task 21.2:
    To prevent target leakage, every rolling and cumulative feature is
    computed on **shifted** data: ``.shift(1)`` is applied before the
    rolling window so that a lap's feature value reflects only completed
    prior laps, never the lap being predicted. This turns what would
    otherwise be a reconstruction metric ("how fast was this lap given
    all surrounding laps?") into a genuine out-of-sample predictor
    ("how fast were the N preceding laps, and how fast will this one be?").

    Consequences:
    - The first lap in each stint/group gets NaN for all rolling features,
      because no prior laps exist. XGBoost handles NaN natively via its
      default direction split.
    - ``delta_to_fastest_s`` uses the *cumulative minimum* of prior laps
      (expanding window on shifted series) instead of the full-group
      minimum, ensuring no future information leaks in.

Design decisions:
    - Rolling is applied on already-sorted data (LapNumber ascending within
      each group). The caller must ensure the DataFrame is sorted before
      calling these functions.
    - The output columns use the ``roll_`` prefix to be unambiguous in the
      Gold-layer feature matrix.
    - No in-place mutation: all functions return a new DataFrame.
"""

import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Default rolling window sizes. Calibrated on 2023-2024 race data.
# 3-lap: captures very recent pace shift (tyre cliff, fuel effect).
# 5-lap: smooths lap-to-lap variability to expose underlying constructor pace.
WINDOW_SHORT: int = 3
WINDOW_LONG: int = 5

# Grouping context for rolling windows: pace is meaningfully comparable only
# within the same driver and tyre stint.
DEFAULT_PACE_GROUPS: list[str] = ["Driver", "Stint"]

# Sort keys ensuring monotone LapNumber within each group before rolling.
DEFAULT_SORT_KEYS: list[str] = ["Driver", "Stint", "LapNumber"]


# ── Public API ────────────────────────────────────────────────────────────────


def add_rolling_pace_features(
    df: pd.DataFrame,
    lap_time_col: str = "LapTime_s",
    group_cols: list[str] | None = None,
    window_short: int = WINDOW_SHORT,
    window_long: int = WINDOW_LONG,
) -> pd.DataFrame:
    """Add rolling mean and standard deviation lap time features.

    Computes per-(Driver, Stint) rolling statistics on ``lap_time_col``:

    - ``roll_laptime_{window_short}``: rolling mean, short window.
    - ``roll_laptime_{window_long}``:  rolling mean, long window.
    - ``roll_std_{window_short}``:     rolling std, short window.
    - ``delta_roll_pace``:             difference between short and long
      rolling mean — positive values indicate the driver is slowing
      (tyre degradation / fuel pick-up), negative indicates improving pace.

    Args:
        df: Clean laps DataFrame from the Silver layer. Must contain
            ``lap_time_col``, ``LapNumber``, and the columns in
            ``group_cols``.
        lap_time_col: Lap time column in decimal seconds.
        group_cols: Grouping columns for per-driver, per-stint rolling.
            Defaults to ``["Driver", "Stint"]``.
        window_short: Short rolling window size in laps.
        window_long: Long rolling window size in laps.

    Returns:
        New DataFrame with four rolling feature columns appended. Row count
        and index are unchanged.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.
        KeyError: If required columns are absent from ``df``.

    Example::

        from f1_predictions.features.rolling_pace import add_rolling_pace_features

        df_feat = add_rolling_pace_features(clean_laps)
        df_feat[["Driver", "LapNumber", "LapTime_s",
                 "roll_laptime_3", "roll_laptime_5", "delta_roll_pace"]].head(10)
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)

    groups = group_cols if group_cols is not None else DEFAULT_PACE_GROUPS
    _assert_columns_present(
        df, [lap_time_col, "LapNumber", *groups], context="add_rolling_pace_features"
    )

    result = df.sort_values(DEFAULT_SORT_KEYS).copy()

    def _causal_rolling_mean(series: pd.Series, window: int) -> pd.Series:
        """Rolling mean on prior laps only (shift(1) enforces t-1 boundary).

        The shift moves the target lap's value out of the window so the mean
        reflects only completed laps. ``min_periods=1`` still applies to the
        shifted series, so the second lap in a stint (which sees one prior
        value after the shift) gets a valid estimate rather than NaN.
        The first lap always returns NaN — correct, since no prior laps exist.
        """
        return series.shift(1).rolling(window=window, min_periods=1).mean()

    def _causal_rolling_std(series: pd.Series, window: int) -> pd.Series:
        """Rolling std on prior laps only (shift(1) enforces t-1 boundary).

        ``min_periods=2`` so that at least two prior values are required for a
        meaningful standard deviation; otherwise NaN is returned.
        """
        return series.shift(1).rolling(window=window, min_periods=2).std()

    short_col = f"roll_laptime_{window_short}"
    long_col = f"roll_laptime_{window_long}"
    std_col = f"roll_std_{window_short}"

    result[short_col] = result.groupby(groups, group_keys=False)[
        lap_time_col
    ].transform(lambda s: _causal_rolling_mean(s, window_short))
    result[long_col] = result.groupby(groups, group_keys=False)[lap_time_col].transform(
        lambda s: _causal_rolling_mean(s, window_long)
    )
    result[std_col] = result.groupby(groups, group_keys=False)[lap_time_col].transform(
        lambda s: _causal_rolling_std(s, window_short)
    )

    # Delta: positive = slowing down (tyre cliff signal).
    # Both components are already causal, so the delta is causal too.
    result["delta_roll_pace"] = result[short_col] - result[long_col]

    n_new_cols = 4
    logger.info(
        "Rolling pace features added (causal t-1): %s | %d new columns "
        "(%s, %s, %s, delta_roll_pace)",
        short_col,
        n_new_cols,
        short_col,
        long_col,
        std_col,
    )
    return result


def add_lap_delta_to_fastest(
    df: pd.DataFrame,
    lap_time_col: str = "LapTime_s",
    group_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Add the gap between each lap and the best *previously completed* lap.

    ``delta_to_fastest_s``: signed gap in seconds to the fastest lap time
    seen **before** the current lap within the group context (Driver,
    EventName). This is the causal (t-1) analogue of the session-minimum
    delta: it tells the model how far behind the driver's own prior best the
    current lap is, without revealing what the driver will achieve later in
    the session.

    Implementation:
        1. Sort by (Driver, EventName, LapNumber) to guarantee chronological
           order within each group.
        2. Shift the lap-time series by one position so each position reflects
           the *previous* lap's time.
        3. Take a cumulative minimum on the shifted series — this gives, for
           each lap, the fastest time recorded in all *prior* laps.
        4. Subtract that expanding minimum from the current lap time.

    Consequence:
        - The first lap in each group returns NaN (no prior lap exists).
        - A driver who sets a new personal best has delta = 0 only from the
          *next* lap onward, not the lap that set the record.

    Args:
        df: Clean laps DataFrame. Must be sortable by LapNumber within groups.
        lap_time_col: Lap time column in decimal seconds.
        group_cols: Grouping context. Defaults to ``["Driver", "EventName"]``.

    Returns:
        New DataFrame with ``delta_to_fastest_s`` column appended.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.
        KeyError: If required columns are absent.
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)

    groups = group_cols if group_cols is not None else ["Driver", "EventName"]
    sort_keys = [*groups, "LapNumber"] if "LapNumber" in df.columns else groups
    _assert_columns_present(
        df, [lap_time_col, *groups], context="add_lap_delta_to_fastest"
    )

    result = df.sort_values(sort_keys).copy()

    def _causal_delta(series: pd.Series) -> pd.Series:
        """Gap to the best *prior* lap (t-1 causal boundary).

        shift(1) pushes the current lap value out of the cummin window so
        the expanding minimum only covers completed laps.
        """
        prior_best = series.shift(1).expanding().min()
        return series - prior_best

    result["delta_to_fastest_s"] = result.groupby(groups, group_keys=False)[
        lap_time_col
    ].transform(_causal_delta)
    logger.info("delta_to_fastest_s feature added (causal t-1 cumulative min).")
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────


def _assert_columns_present(
    df: pd.DataFrame,
    required: list[str],
    context: str = "",
) -> None:
    """Raise KeyError if any required columns are absent from df.

    Args:
        df: DataFrame to check.
        required: Column names that must be present.
        context: Function name for the error message (for debugging).

    Raises:
        KeyError: If one or more required columns are missing.
    """
    missing = [c for c in required if c not in df.columns]
    if missing:
        msg = (
            f"[{context}] Required column(s) missing from DataFrame: {missing}. "
            f"Available: {list(df.columns)}"
        )
        raise KeyError(msg)
