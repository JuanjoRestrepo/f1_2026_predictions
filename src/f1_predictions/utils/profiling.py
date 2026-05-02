"""Lightweight DataFrame profiling utilities for the f1_predictions pipeline.

Rationale:
    sweetviz generates a full HTML report (useful once per dataset).
    missingno visualizes missing value patterns (used in EDA notebooks).
    This module covers the third use case: a fast, zero-dependency diagnostic
    printout that runs in under a second and is safe to call inside any
    pipeline function for inline observability.

    quick_profile() is the pandas-native alternative to ydata-profiling's
    ProfileReport for routine inspection. It is NOT a replacement for sweetviz
    — use sweetviz when you need a shareable HTML report, use quick_profile
    when you need a 5-second sanity check during development or pipeline runs.

Usage::

    from f1_predictions.utils.profiling import quick_profile

    quick_profile(df_laps, name="Laps - Bahrain 2025")
"""

import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)


def quick_profile(df: pd.DataFrame, name: str = "DataFrame") -> None:
    """Print a compact diagnostic profile of a DataFrame to stdout.

    Covers the core questions of every initial inspection:
        1. Shape and column count.
        2. Which columns have nulls and what percentage.
        3. Descriptive statistics with tail percentiles (5th, 95th).
        4. Duplicate row count.

    This function is intentionally side-effect-only (no return value) and
    uses print() rather than logging because it is an interactive diagnostic
    tool for notebooks, not a pipeline event to be recorded in log files.

    Args:
        df: The DataFrame to profile. Must not be empty.
        name: A human-readable label for the profile header. Use the format
            "<entity> - <context>", e.g., "Laps - Bahrain 2025 Race".

    Raises:
        TypeError: If df is not a pandas DataFrame.
        ValueError: If df is empty (zero rows).

    Example::

        import fastf1
        from f1_predictions.utils.profiling import quick_profile

        session = fastf1.get_session(2025, 1, "R")
        session.load()
        quick_profile(session.laps, name="Laps - Bahrain 2025 Race")
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)
    if df.empty:
        msg = f"DataFrame '{name}' is empty — nothing to profile."
        raise ValueError(msg)

    separator = "=" * 64

    print(f"\n{separator}")
    print(f"  PROFILE: {name}")
    print(f"  Shape  : {df.shape[0]:,} rows x {df.shape[1]} columns")
    print(f"{separator}")

    # ── Null summary ─────────────────────────────────────────────────────
    null_counts = df.isnull().sum()
    null_pct = (df.isnull().mean() * 100).round(2)
    nunique = df.nunique()

    null_summary = pd.DataFrame(
        {
            "dtype": df.dtypes,
            "nulls": null_counts,
            "null_%": null_pct,
            "nunique": nunique,
        }
    )
    cols_with_nulls = null_summary[null_summary["nulls"] > 0]

    print(f"\n{'── Null columns':-<64}")
    if cols_with_nulls.empty:
        print("  ✓ No null values detected.")
    else:
        print(cols_with_nulls.to_string())

    # Log null columns as a warning so they appear in the pipeline log file
    # even when this function is called from a notebook.
    if not cols_with_nulls.empty:
        logger.warning(
            "Null values detected in '%s': %d column(s) affected — see profile output.",
            name,
            len(cols_with_nulls),
        )

    # ── Full column overview (always printed) ────────────────────────────
    print(f"\n{'── All columns':-<64}")
    print(null_summary.to_string())

    # ── Descriptive statistics (numeric only) ────────────────────────────
    numeric_df = df.select_dtypes(include="number")
    if not numeric_df.empty:
        print(f"\n{'── Descriptive statistics (numeric)':-<64}")
        print(
            numeric_df.describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).T.to_string()
        )
    else:
        print(f"\n{'── Descriptive statistics':-<64}")
        print("  No numeric columns found.")

    # ── Categorical preview ───────────────────────────────────────────────
    cat_df = df.select_dtypes(include=["object", "category"])
    if not cat_df.empty:
        print(f"\n{'── Categorical columns (top 5 values)':-<64}")
        for col in cat_df.columns:
            top = df[col].value_counts().head(5)
            print(f"\n  {col}:")
            print(top.to_string(header=False))

    # ── Duplicates ────────────────────────────────────────────────────────
    n_dupes = int(df.duplicated().sum())
    print(f"\n{'── Duplicates':-<64}")
    if n_dupes == 0:
        print("  ✓ No duplicate rows detected.")
    else:
        print(f"  ⚠ {n_dupes:,} duplicate row(s) detected.")
        logger.warning(
            "Duplicate rows in '%s': %d row(s) — investigate before cleaning.",
            name,
            n_dupes,
        )

    print(f"\n{separator}\n")
