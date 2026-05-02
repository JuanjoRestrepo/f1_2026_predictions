"""Lap time normalization for the f1_predictions cleaning stage.

Responsibilities:
    1. Convert pandas Timedelta lap/sector times to decimal seconds (float64).
       Timedeltas cannot be used directly as model features — XGBoost and
       scikit-learn require numeric inputs. Decimal seconds are the canonical
       unit for all timing columns in the Silver layer.
    2. Standardize driver abbreviations and team names to a canonical mapping.
       FastF1 returns team names inconsistently across seasons (e.g.
       "Red Bull Racing" vs "Oracle Red Bull Racing" vs "Red Bull"). A single
       canonical name per constructor is required for one-hot encoding and
       for joining qualifying/race data across rounds.

Design decisions:
    - All normalization functions are pure: they take a DataFrame, return a
      new DataFrame, and never mutate the input. This guarantees idempotency
      when the cleaning pipeline is re-run on the same Parquet file.
    - Column name constants are imported from session_loader to avoid
      string duplication across modules.
    - The canonical team map is defined here as a module-level constant so it
      can be imported and inspected in notebooks without instantiating a class.
      When a new constructor enters the grid, add it here and bump the version.

Timedelta → seconds rationale:
    ``pd.Timedelta.total_seconds()`` is the lossless conversion path.
    Alternatives considered and rejected:
        - ``.value`` (nanoseconds): technically correct but semantically
          opaque in feature engineering and reporting.
        - ``pd.to_numeric()``: works but loses the explicit domain intent.
        - Vectorised ``.dt.total_seconds()``: used here — it is the pandas-
          native vectorised operation, ~20x faster than row-wise apply.
"""

from collections.abc import Sequence

import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Version ───────────────────────────────────────────────────────────────────

# Bump when the canonical team map or column list changes.
# Downstream stages can assert on this version to detect stale cached data.
NORMALIZER_VERSION: str = "1.0.0"

# ── Timedelta columns ─────────────────────────────────────────────────────────

# All Timedelta columns present in the raw laps DataFrame that need conversion.
# These map to <ColumnName>_s (seconds) in the output.
# Rationale: explicit list prevents silent misses if FastF1 adds new timing
# columns in a future release — the pipeline log will surface any unmapped col.
TIMEDELTA_LAP_COLUMNS: tuple[str, ...] = (
    "LapTime",
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    "PitInTime",
    "PitOutTime",
)

# ── Canonical team map ────────────────────────────────────────────────────────

# Maps every known FastF1 team name variant to a canonical short name.
# Canonical names are stable across seasons and used as category labels
# throughout the pipeline (OHE, SHAP plots, report tables).
#
# Maintenance: when a constructor rebrands or a new team joins, add an entry.
# Do NOT delete old variants — historical data will still carry the old name.
CANONICAL_TEAM_MAP: dict[str, str] = {
    # Red Bull
    "Red Bull Racing": "Red Bull",
    "Oracle Red Bull Racing": "Red Bull",
    "Red Bull Racing Honda": "Red Bull",
    # Mercedes
    "Mercedes": "Mercedes",
    "Mercedes-AMG Petronas F1 Team": "Mercedes",
    "Mercedes-AMG Petronas": "Mercedes",
    # Ferrari
    "Ferrari": "Ferrari",
    "Scuderia Ferrari": "Ferrari",
    "Scuderia Ferrari HP": "Ferrari",
    # McLaren
    "McLaren": "McLaren",
    "McLaren F1 Team": "McLaren",
    "McLaren Mercedes": "McLaren",
    # Aston Martin
    "Aston Martin": "Aston Martin",
    "Aston Martin Aramco": "Aston Martin",
    "Aston Martin F1 Team": "Aston Martin",
    # Alpine / Renault
    "Alpine": "Alpine",
    "Alpine F1 Team": "Alpine",
    "Renault": "Alpine",
    "BWT Alpine F1 Team": "Alpine",
    # Williams
    "Williams": "Williams",
    "Williams Racing": "Williams",
    # AlphaTauri / RB / Toro Rosso
    "AlphaTauri": "RB",
    "Scuderia AlphaTauri": "RB",
    "Scuderia AlphaTauri Honda": "RB",
    "RB": "RB",
    "Visa Cash App RB": "RB",
    "Toro Rosso": "RB",
    # Alfa Romeo / Sauber / Kick Sauber
    "Alfa Romeo": "Sauber",
    "Alfa Romeo Racing": "Sauber",
    "Sauber": "Sauber",
    "Kick Sauber": "Sauber",
    "Stake F1 Team Kick Sauber": "Sauber",
    # Haas
    "Haas F1 Team": "Haas",
    "Haas": "Haas",
    "MoneyGram Haas F1 Team": "Haas",
}


# ── Internal helpers ──────────────────────────────────────────────────────────


def _timedelta_col_to_seconds(series: pd.Series) -> pd.Series:
    """Convert a Timedelta Series to float64 seconds.

    Uses the vectorised ``.dt.total_seconds()`` accessor. NaT values are
    preserved as NaN (float64) so downstream imputation can handle them.

    Args:
        series: A pandas Series with dtype ``timedelta64[ns]`` or object.
            Non-Timedelta series are returned unchanged with a warning.

    Returns:
        A float64 Series of decimal seconds, or the original series if the
        dtype is not a recognised Timedelta type.
    """
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds()  # type: ignore[no-any-return]
    # Already numeric (e.g., re-running normalizer on a partially processed df)
    if pd.api.types.is_numeric_dtype(series):
        logger.debug(
            "Column '%s' is already numeric — skipping conversion.", series.name
        )
        return series
    logger.warning(
        "Column '%s' has unexpected dtype '%s' — returning unchanged.",
        series.name,
        series.dtype,
    )
    return series


# ── Public API ────────────────────────────────────────────────────────────────


def convert_timedeltas_to_seconds(
    df: pd.DataFrame,
    columns: Sequence[str] | None = None,
    drop_original: bool = True,
) -> pd.DataFrame:
    """Convert Timedelta timing columns to decimal seconds (float64).

    For each column in ``columns`` that exists in ``df``, a new column
    ``<col>_s`` is added with the decimal-seconds value. The original
    Timedelta column is dropped when ``drop_original=True`` (default) to
    keep the Silver-layer DataFrame free of mixed-type timing representations.

    Args:
        df: Raw laps DataFrame from the ingestion stage. Not mutated.
        columns: Columns to convert. Defaults to ``TIMEDELTA_LAP_COLUMNS``
            when ``None``. Pass a custom list to convert a subset.
        drop_original: When ``True``, remove the original Timedelta columns
            after creating the ``_s`` variants. Set to ``False`` for debugging.

    Returns:
        A new DataFrame with ``_s`` columns added and, optionally, the
        original Timedelta columns removed.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.

    Example::

        from f1_predictions.cleaning.normalizer import convert_timedeltas_to_seconds

        clean_laps = convert_timedeltas_to_seconds(raw_laps)
        # raw_laps["LapTime"]   → timedelta64
        # clean_laps["LapTime_s"] → float64 seconds (e.g. 90.123)
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)

    cols_to_convert = (
        list(columns) if columns is not None else list(TIMEDELTA_LAP_COLUMNS)
    )
    result = df.copy()
    converted: list[str] = []
    skipped: list[str] = []

    for col in cols_to_convert:
        if col not in result.columns:
            skipped.append(col)
            continue
        result[f"{col}_s"] = _timedelta_col_to_seconds(result[col])
        converted.append(col)

    if skipped:
        logger.debug(
            "Timedelta conversion: %d column(s) not found in DataFrame — skipped: %s",
            len(skipped),
            skipped,
        )

    if drop_original and converted:
        result = result.drop(columns=converted)

    logger.info(
        "Timedelta conversion complete: %d converted → _s suffix, %d skipped.",
        len(converted),
        len(skipped),
    )
    return result


def standardize_team_names(
    df: pd.DataFrame,
    team_column: str = "Team",
    canonical_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Map raw FastF1 team names to canonical constructor labels.

    Applies ``CANONICAL_TEAM_MAP`` (or a custom override map) to the
    ``team_column``. Unknown team names are preserved unchanged and logged
    as warnings so new constructors are surfaced immediately rather than
    silently producing unmapped values in one-hot encoding.

    Args:
        df: Laps or results DataFrame containing a team name column.
        team_column: Name of the column holding raw constructor names.
            Defaults to ``"Team"`` (laps DataFrame convention).
        canonical_map: Override the default ``CANONICAL_TEAM_MAP``. Useful
            in tests or when extending the map for a specific season.

    Returns:
        A new DataFrame with ``team_column`` values replaced by their
        canonical equivalents. Unknown values are left unchanged.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.
        KeyError: If ``team_column`` does not exist in ``df``.

    Example::

        clean_laps = standardize_team_names(raw_laps)
        # "Oracle Red Bull Racing" → "Red Bull"
        # "Scuderia Ferrari HP"   → "Ferrari"
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)
    if team_column not in df.columns:
        msg = (
            f"Column '{team_column}' not found in DataFrame. "
            f"Available: {list(df.columns)}"
        )
        raise KeyError(msg)

    mapping = canonical_map if canonical_map is not None else CANONICAL_TEAM_MAP
    result = df.copy()

    original_values = result[team_column].unique()
    result[team_column] = result[team_column].map(mapping).fillna(result[team_column])
    mapped_values = result[team_column].unique()

    # Surface unknown (unmapped) team names — these need to be added to the map
    unknown = set(original_values) - set(mapping.keys())
    if unknown:
        logger.warning(
            "Unknown team names not in CANONICAL_TEAM_MAP (%d): %s — "
            "values preserved unchanged. Add them to normalizer.CANONICAL_TEAM_MAP.",
            len(unknown),
            sorted(unknown),
        )
    else:
        logger.info(
            "Team name standardization complete. Canonical constructors: %s",
            sorted(mapped_values),
        )

    return result


def standardize_driver_identifiers(
    df: pd.DataFrame,
    driver_column: str = "Driver",
) -> pd.DataFrame:
    """Normalize driver abbreviation column to uppercase, strip whitespace.

    FastF1 driver codes are already three uppercase letters, but edge cases
    exist: test sessions, display format inconsistencies, and rookie drivers
    with non-standard codes. This function enforces a clean string format
    without requiring a hardcoded driver map (which would need updating every
    season).

    Args:
        df: DataFrame containing a driver abbreviation column.
        driver_column: Column name for the driver identifier.
            Defaults to ``"Driver"``.

    Returns:
        A new DataFrame with ``driver_column`` values stripped and uppercased.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.
        KeyError: If ``driver_column`` does not exist in ``df``.
    """
    if not isinstance(df, pd.DataFrame):
        msg = f"Expected pd.DataFrame, got {type(df).__name__}"
        raise TypeError(msg)
    if driver_column not in df.columns:
        msg = f"Column '{driver_column}' not found. Available: {list(df.columns)}"
        raise KeyError(msg)

    result = df.copy()
    result[driver_column] = result[driver_column].str.strip().str.upper()
    logger.debug(
        "Driver identifier normalization complete on column '%s'.", driver_column
    )
    return result
