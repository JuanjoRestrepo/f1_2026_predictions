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

    ``min_periods=1`` is used so drivers with fewer than N laps in a stint
    still get a valid rolling value rather than NaN. This matters for short
    opening stints and for drivers with early DNFs.

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

    def _rolling_mean(series: pd.Series, window: int) -> pd.Series:
        """Apply rolling mean within group, preserving NaN semantics."""
        return series.rolling(window=window, min_periods=1).mean()

    def _rolling_std(series: pd.Series, window: int) -> pd.Series:
        """Apply rolling std within group; NaN for single-lap groups."""
        return series.rolling(window=window, min_periods=2).std()

    short_col = f"roll_laptime_{window_short}"
    long_col = f"roll_laptime_{window_long}"
    std_col = f"roll_std_{window_short}"

    result[short_col] = result.groupby(groups, group_keys=False)[
        lap_time_col
    ].transform(lambda s: _rolling_mean(s, window_short))
    result[long_col] = result.groupby(groups, group_keys=False)[lap_time_col].transform(
        lambda s: _rolling_mean(s, window_long)
    )
    result[std_col] = result.groupby(groups, group_keys=False)[lap_time_col].transform(
        lambda s: _rolling_std(s, window_short)
    )

    # Delta: positive = slowing down (tyre cliff signal).
    result["delta_roll_pace"] = result[short_col] - result[long_col]

    n_new_cols = 4
    logger.info(
        "Rolling pace features added: %s | %d new columns "
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
    """Add the gap between each lap and the session's fastest clean lap.

    ``delta_to_fastest_s``: signed gap in seconds to the minimum lap time
    in the group context (Driver, EventName). Represents how far a given
    lap is from the driver's best representative pace at this circuit.

    Args:
        df: Clean laps DataFrame.
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
    _assert_columns_present(
        df, [lap_time_col, *groups], context="add_lap_delta_to_fastest"
    )

    result = df.copy()
    result["delta_to_fastest_s"] = result.groupby(groups, group_keys=False)[
        lap_time_col
    ].transform(lambda s: s - s.min())
    logger.info("delta_to_fastest_s feature added.")
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
