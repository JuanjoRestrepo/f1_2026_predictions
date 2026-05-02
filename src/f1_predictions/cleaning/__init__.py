"""Cleaning package for the f1_predictions pipeline.

Transforms raw ingestion-layer DataFrames into analysis-ready Silver-layer
Parquet files. All functions are pure (copy semantics) and idempotent.

Public API:

Normalization::

    convert_timedeltas_to_seconds  : Timedelta columns → float64 seconds (_s).
    standardize_team_names         : Raw constructor names → canonical labels.
    standardize_driver_identifiers : Strip and uppercase driver codes.
    CANONICAL_TEAM_MAP             : Dict of all known constructor name variants.
    TIMEDELTA_LAP_COLUMNS          : Tuple of default Timedelta column names.

Outlier filtering::

    apply_all_filters        : Composed full filter sequence + stats dict.
    filter_out_laps          : Remove pit-exit laps.
    filter_in_laps           : Remove pit-entry laps.
    filter_neutralised_laps  : Remove yellow flag / SC / VSC laps.
    filter_impossible_lap_times : Remove NaN and out-of-range lap times.
    filter_statistical_outliers : MAD-based slow lap removal per driver/stint.

Imputation::

    run_imputation_pipeline  : Full imputation sequence + audit dict.
    drop_null_lap_times      : Drop rows with null lap time (no target).
    impute_tyre_data         : ffill TyreLife, mode-fill Compound.
    impute_speed_traps       : Median-fill speed trap nulls per driver/circuit.

Pipeline orchestration::

    run_cleaning_pipeline    : Full cleaning run for one session → Silver Parquet.
    load_clean_laps          : Read Silver-layer clean laps for a session.
    CleaningReport           : Dataclass returned by run_cleaning_pipeline().
"""

from f1_predictions.cleaning.imputer import (
    drop_null_lap_times,
    impute_speed_traps,
    impute_tyre_data,
    run_imputation_pipeline,
)
from f1_predictions.cleaning.normalizer import (
    CANONICAL_TEAM_MAP,
    TIMEDELTA_LAP_COLUMNS,
    convert_timedeltas_to_seconds,
    standardize_driver_identifiers,
    standardize_team_names,
)
from f1_predictions.cleaning.outlier_filter import (
    DEFAULT_Z_THRESHOLD,
    apply_all_filters,
    filter_impossible_lap_times,
    filter_in_laps,
    filter_neutralised_laps,
    filter_out_laps,
    filter_statistical_outliers,
)
from f1_predictions.cleaning.pipeline import (
    CleaningReport,
    load_clean_laps,
    run_cleaning_pipeline,
)

__all__ = [
    # Normalizer
    "CANONICAL_TEAM_MAP",
    # Outlier filter
    "DEFAULT_Z_THRESHOLD",
    "TIMEDELTA_LAP_COLUMNS",
    # Pipeline
    "CleaningReport",
    "apply_all_filters",
    "convert_timedeltas_to_seconds",
    # Imputer
    "drop_null_lap_times",
    "filter_impossible_lap_times",
    "filter_in_laps",
    "filter_neutralised_laps",
    "filter_out_laps",
    "filter_statistical_outliers",
    "impute_speed_traps",
    "impute_tyre_data",
    "load_clean_laps",
    "run_cleaning_pipeline",
    "run_imputation_pipeline",
    "standardize_driver_identifiers",
    "standardize_team_names",
]
