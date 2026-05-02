"""Null imputation strategies for the f1_predictions cleaning stage.

Rationale for each imputation strategy:

    ``LapTime_s`` (after outlier filter):
        After ``filter_impossible_lap_times()`` and ``apply_all_filters()``,
        remaining NaN lap times indicate genuinely incomplete laps (red-flag
        stoppage mid-lap, sensor loss, etc.). These rows provide no target
        variable and must be **dropped**, not imputed. Imputing a lap time
        would fabricate training signal.

    ``TyreLife`` / ``Stint``:
        Forward-fill within (Driver, Stint) groups. Tyre life increments by 1
        each lap; a null in the middle is a sensor gap, not a real gap. ffill()
        is the correct strategy because the previous lap's tyre life is the
        best estimate for the current lap.

    ``Compound``:
        Mode imputation within (Driver, Stint) group. A driver cannot change
        compounds within a stint, so the most frequent compound in the stint
        is the correct value for any null rows.

    Speed trap columns (``SpeedI1``, ``SpeedI2``, ``SpeedFL``, ``SpeedST``):
        Median imputation within (Driver, Circuit) — using the circuit-level
        median because speed trap readings are strongly circuit-dependent
        (Monza speeds are incomparable to Monaco speeds). Median is preferred
        over mean to avoid sensitivity to the outliers that passed filtering.

    All other columns:
        Left as NaN. The modeling stage handles residual nulls via
        XGBoost's native missing-value handling (learns split direction for
        NaN). We do not fabricate values for columns not explicitly listed here.

Imputation audit:
    All functions return both the imputed DataFrame and an audit dict so the
    cleaning notebook can log exactly how many values were imputed per column.
    This is critical for reproducibility — if imputation counts change between
    pipeline runs on the same data, it signals an upstream data quality issue.
"""

import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Column groups ─────────────────────────────────────────────────────────────

# Speed trap columns present after Timedelta conversion (no _s suffix —
# these were already float in FastF1 output).
SPEED_TRAP_COLUMNS: tuple[str, ...] = ("SpeedI1", "SpeedI2", "SpeedFL", "SpeedST")


# ── Internal helpers ──────────────────────────────────────────────────────────


def _count_nulls(df: pd.DataFrame, columns: list[str]) -> dict[str, int]:
    """Count nulls per column before imputation for the audit log.

    Args:
        df: DataFrame to inspect.
        columns: Column names to count nulls for. Columns absent from
            ``df`` are excluded silently.

    Returns:
        Dict mapping column name → null count.
    """
    return {col: int(df[col].isna().sum()) for col in columns if col in df.columns}


# ── Public API ────────────────────────────────────────────────────────────────


def drop_null_lap_times(
    df: pd.DataFrame,
    lap_time_col: str = "LapTime_s",
) -> tuple[pd.DataFrame, int]:
    """Drop rows where the converted lap time is null.

    Called after ``apply_all_filters()``. At this point, remaining NaN lap
    times represent genuinely uncompletable laps (mid-lap red flag, session
    abort). Imputing these would fabricate training targets — they are dropped.

    Args:
        df: Filtered laps DataFrame.
        lap_time_col: Lap time column in decimal seconds.

    Returns:
        A tuple of (filtered DataFrame, number of rows dropped).
    """
    if lap_time_col not in df.columns:
        logger.warning(
            "Column '%s' not found — null lap time drop skipped.", lap_time_col
        )
        return df, 0

    null_mask = df[lap_time_col].isna()
    n_dropped = int(null_mask.sum())
    result = df[~null_mask].copy()

    if n_dropped > 0:
        logger.warning(
            "Dropped %d row(s) with null '%s' after outlier filtering. "
            "These represent incomplete laps (red flag stoppage, sensor loss).",
            n_dropped,
            lap_time_col,
        )
    else:
        logger.debug("No null '%s' rows to drop.", lap_time_col)

    return result, n_dropped


def impute_tyre_data(
    df: pd.DataFrame,
    group_cols: list[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Forward-fill TyreLife and mode-impute Compound within Driver/Stint groups.

    ``TyreLife``: increments by 1 each lap. A null mid-stint is a sensor gap;
    forward-fill (then backward-fill for the first lap of the stint) is
    the correct strategy.

    ``Stint``: forward-fill within Driver groups. If Stint is null on a lap,
    it inherits the previous lap's stint number.

    ``Compound``: mode within (Driver, Stint). A driver cannot change compounds
    within a stint — the most frequent value is the ground truth.

    Args:
        df: Laps DataFrame containing tyre columns.
        group_cols: Grouping context. Defaults to ``["Driver", "Stint"]``.

    Returns:
        A tuple of:
            - Imputed DataFrame.
            - Audit dict: column → number of values imputed.
    """
    groups = group_cols if group_cols is not None else ["Driver", "Stint"]
    result = df.copy()
    audit: dict[str, int] = {}

    # ── Stint: ffill within Driver ────────────────────────────────────────
    if "Stint" in result.columns and "Driver" in result.columns:
        before = int(result["Stint"].isna().sum())
        result["Stint"] = result.groupby("Driver", group_keys=False)["Stint"].transform(
            lambda s: s.ffill().bfill()
        )
        audit["Stint"] = before - int(result["Stint"].isna().sum())

    # ── TyreLife: ffill + bfill within (Driver, Stint) ───────────────────
    if "TyreLife" in result.columns:
        before = int(result["TyreLife"].isna().sum())
        result["TyreLife"] = result.groupby(groups, group_keys=False)[
            "TyreLife"
        ].transform(lambda s: s.ffill().bfill())
        audit["TyreLife"] = before - int(result["TyreLife"].isna().sum())

    # ── Compound: mode within (Driver, Stint) ────────────────────────────
    if "Compound" in result.columns:
        before = int(result["Compound"].isna().sum())

        def _mode_fill(series: pd.Series) -> pd.Series:
            """Fill NaN with the mode of the group. Return unchanged if no mode."""
            mode_vals = series.dropna().mode()
            if mode_vals.empty:
                return series
            return series.fillna(mode_vals.iloc[0])

        result["Compound"] = result.groupby(groups, group_keys=False)[
            "Compound"
        ].transform(_mode_fill)
        audit["Compound"] = before - int(result["Compound"].isna().sum())

    imputed_total = sum(audit.values())
    logger.info(
        "Tyre imputation complete: %d total values imputed. Breakdown: %s",
        imputed_total,
        audit,
    )
    return result, audit


def impute_speed_traps(
    df: pd.DataFrame,
    group_cols: list[str] | None = None,
    columns: tuple[str, ...] = SPEED_TRAP_COLUMNS,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Median-impute speed trap columns within (Driver, circuit) groups.

    Speed trap readings are strongly circuit-dependent. Bahrain I1 speeds
    are fundamentally incomparable to Monza I1 speeds, so imputation must
    be circuit-scoped. Within a circuit, a driver's median speed over the
    session is the best estimate for a null reading caused by a sensor failure.

    The circuit grouping column is ``"EventName"`` (from metadata injection),
    which encodes the circuit without requiring a separate circuit ID column.

    Args:
        df: Laps DataFrame with speed trap columns.
        group_cols: Grouping context. Defaults to ``["Driver", "EventName"]``.
        columns: Speed trap column names to impute.

    Returns:
        A tuple of:
            - Imputed DataFrame.
            - Audit dict: column → number of values imputed.
    """
    groups = group_cols if group_cols is not None else ["Driver", "EventName"]
    result = df.copy()
    audit: dict[str, int] = {}

    for col in columns:
        if col not in result.columns:
            logger.debug("Speed trap column '%s' not found — skipped.", col)
            continue

        before = int(result[col].isna().sum())
        if before == 0:
            audit[col] = 0
            continue

        # Check that all group columns exist
        missing_groups = [c for c in groups if c not in result.columns]
        if missing_groups:
            logger.warning(
                "Group column(s) %s missing — falling back to global median for '%s'.",
                missing_groups,
                col,
            )
            result[col] = result[col].fillna(result[col].median())
        else:
            result[col] = result.groupby(groups, group_keys=False)[col].transform(
                lambda s: s if s.isna().all() else s.fillna(s.median())
            )

        after = int(result[col].isna().sum())
        imputed = before - after
        audit[col] = imputed

        if after > 0:
            # Residual nulls after group median: fall back to global median
            global_median = result[col].median()
            result[col] = result[col].fillna(global_median)
            residual_imputed = after - int(result[col].isna().sum())
            logger.debug(
                "Speed trap '%s': %d residual nulls after group median — "
                "filled with global median (%.2f).",
                col,
                after,
                global_median,
            )
            audit[col] += residual_imputed

    imputed_total = sum(audit.values())
    logger.info(
        "Speed trap imputation complete: %d total values imputed. Breakdown: %s",
        imputed_total,
        audit,
    )
    return result, audit


def run_imputation_pipeline(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Execute the full imputation sequence and return an aggregated audit log.

    Sequence:
        1. ``drop_null_lap_times()``  — drop uncompletable laps (no target).
        2. ``impute_tyre_data()``     — ffill TyreLife, mode Compound.
        3. ``impute_speed_traps()``   — median-fill speed trap nulls.

    Args:
        df: Filtered laps DataFrame from ``apply_all_filters()``.

    Returns:
        A tuple of:
            - The fully imputed DataFrame.
            - Aggregated audit dict with keys:
                ``"dropped_null_lap_times"``: rows dropped.
                ``"tyre"``: per-column imputation counts.
                ``"speed_traps"``: per-column imputation counts.

    Example::

        from f1_predictions.cleaning.imputer import run_imputation_pipeline

        imputed_laps, audit = run_imputation_pipeline(filtered_laps)
        logger.info("Imputation audit: %s", audit)
    """
    full_audit: dict[str, object] = {}

    df1, n_dropped = drop_null_lap_times(df)
    full_audit["dropped_null_lap_times"] = n_dropped

    df2, tyre_audit = impute_tyre_data(df1)
    full_audit["tyre"] = tyre_audit

    df3, speed_audit = impute_speed_traps(df2)
    full_audit["speed_traps"] = speed_audit

    logger.info("Full imputation pipeline complete. Audit: %s", full_audit)
    return df3, full_audit
