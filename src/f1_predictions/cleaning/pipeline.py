"""Cleaning pipeline orchestrator for the f1_predictions pipeline.

This module is the single entry point for the cleaning stage. It:
    1. Reads raw Parquet from the ingestion layer.
    2. Applies normalizer → outlier filter → imputer in order.
    3. Writes clean Parquet to the ``data/processed/`` layer.
    4. Returns a ``CleaningReport`` dataclass summarising every
       transformation applied, for auditability and notebook inspection.

Idempotency guarantee:
    ``run_cleaning_pipeline()`` checks whether a processed Parquet file
    already exists. If it does and ``overwrite=False`` (default), it reads
    and returns the existing file without re-running the cleaning logic.
    This makes it safe to re-run the full notebook without duplicating work.

Layer semantics:
    Raw layer   (data/raw/)       → ingestion output, never modified post-write.
    Silver layer (data/processed/) → cleaning output written here.
    Gold layer  (data/outputs/)   → modeling/feature outputs.

Caller pattern::

    from f1_predictions.ingestion import SessionKey
    from f1_predictions.cleaning.pipeline import run_cleaning_pipeline

    key = SessionKey(year=2025, round_number=1, identifier="R", event_name="Bahrain GP")
    report = run_cleaning_pipeline(key, session_type="race")
    print(report.retention_pct)
"""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from f1_predictions.cleaning.imputer import run_imputation_pipeline
from f1_predictions.cleaning.normalizer import (
    convert_timedeltas_to_seconds,
    standardize_driver_identifiers,
    standardize_team_names,
)
from f1_predictions.cleaning.outlier_filter import apply_all_filters
from f1_predictions.ingestion.fastf1_client import SessionKey
from f1_predictions.ingestion.parquet_writer import (
    DataType,
    read_parquet,
    write_parquet,
)
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Report dataclass ──────────────────────────────────────────────────────────


@dataclass
class CleaningReport:
    """Summary of every transformation applied during the cleaning stage.

    Returned by ``run_cleaning_pipeline()`` for notebook inspection and
    pipeline logging. All counts are integer row-level counts.

    Attributes:
        key: The ``SessionKey`` identifying the session cleaned.
        session_type: ``"race"`` or ``"qualifying"``.
        raw_row_count: Row count before any cleaning.
        clean_row_count: Row count after all cleaning steps.
        retention_pct: Percentage of rows retained.
        filter_stats: Outlier filter breakdown (from ``apply_all_filters()``).
        imputation_audit: Imputation counts per column group.
        output_path: Path to the written Silver-layer Parquet file.
        skipped: True if cleaning was skipped (file already existed).
    """

    key: SessionKey
    session_type: str
    raw_row_count: int = 0
    clean_row_count: int = 0
    retention_pct: float = 0.0
    filter_stats: dict[str, int | float] = field(default_factory=dict)
    imputation_audit: dict[str, object] = field(default_factory=dict)
    output_path: Path | None = None
    skipped: bool = False


# ── Public API ────────────────────────────────────────────────────────────────


def run_cleaning_pipeline(
    key: SessionKey,
    session_type: str = "race",
    overwrite: bool = False,
    raw_base_dir: Path | None = None,
    processed_base_dir: Path | None = None,
) -> CleaningReport:
    """Execute the full cleaning pipeline for a single session.

    Reads raw laps Parquet → normalizes → filters → imputes → writes Silver.

    Args:
        key: The ``SessionKey`` for the session to clean.
        session_type: ``"race"`` or ``"qualifying"``. Controls which raw
            Parquet file is read and which processed file is written.
        overwrite: If ``True``, re-run cleaning even if the Silver Parquet
            already exists. Defaults to ``False`` (idempotent).
        raw_base_dir: Override for the raw data base directory.
            Defaults to ``Settings.data_raw_dir``.
        processed_base_dir: Override for the processed data base directory.
            Defaults to ``Settings.data_processed_dir``.

    Returns:
        A ``CleaningReport`` summarising all transformations applied.

    Raises:
        FileNotFoundError: If the raw Parquet file does not exist.
            Run the ingestion stage first.
        ValueError: If ``session_type`` is not ``"race"`` or ``"qualifying"``.

    Example::

        key = SessionKey(2025, 1, "R", "Bahrain Grand Prix")
        report = run_cleaning_pipeline(key, session_type="race")
        print(f"Retained {report.retention_pct:.1f}% of laps")
        print(f"Written to: {report.output_path}")
    """
    if session_type not in {"race", "qualifying"}:
        msg = f"session_type must be 'race' or 'qualifying'. Got '{session_type}'."
        raise ValueError(msg)

    settings = get_settings()
    raw_dir = raw_base_dir or settings.data_raw_dir
    processed_dir = processed_base_dir or settings.data_processed_dir

    report = CleaningReport(key=key, session_type=session_type)

    # ── Check Silver layer idempotency ────────────────────────────────────
    try:
        existing_path = _resolve_processed_path(key, processed_dir)
        if existing_path.exists() and not overwrite:
            logger.info(
                "Silver Parquet already exists, skipping cleaning "
                "(overwrite=False): %s",
                existing_path,
            )
            report.skipped = True
            report.output_path = existing_path
            return report
    except Exception as e:
        logger.debug(
            "Path resolution failed — proceed with normal cleaning",
            exc_info=e,
        )

    # ── Step 1: Read raw laps ─────────────────────────────────────────────
    logger.info("Cleaning pipeline starting: %s [%s]", key, session_type)
    raw_laps = read_parquet(key, DataType.LAPS, base_dir=raw_dir)
    report.raw_row_count = len(raw_laps)
    logger.info("Raw laps loaded: %d rows", report.raw_row_count)

    # ── Step 2: Normalize ─────────────────────────────────────────────────
    logger.info("Step 2/5 — Timedelta conversion")
    laps = convert_timedeltas_to_seconds(raw_laps)

    logger.info("Step 3/5 — Driver and team standardization")
    laps = standardize_driver_identifiers(laps)

    # Results column is "Team" in laps, "TeamName" in results
    team_col = "Team" if "Team" in laps.columns else "TeamName"
    laps = standardize_team_names(laps, team_column=team_col)

    # ── Step 3: Outlier filtering ─────────────────────────────────────────
    logger.info("Step 4/5 — Outlier filtering")
    laps, filter_stats = apply_all_filters(laps)
    report.filter_stats = filter_stats

    # ── Step 4: Imputation ────────────────────────────────────────────────
    logger.info("Step 5/5 — Null imputation")
    laps, imputation_audit = run_imputation_pipeline(laps)
    report.imputation_audit = imputation_audit

    # ── Step 5: Weather Passthrough (Bronze -> Silver) ────────────────────
    try:
        raw_weather = read_parquet(key, DataType.WEATHER, base_dir=raw_dir)
        if not raw_weather.empty:
            logger.info("Weather data found in Raw layer. Migrating to Silver.")
            write_parquet(
                df=raw_weather,
                key=key,
                data_type=DataType.WEATHER,
                base_dir=processed_dir,
                overwrite=overwrite,
            )
    except FileNotFoundError:
        logger.debug("No weather data in Raw layer for %s", key)

    # ── Step 5: Write Silver Parquet ──────────────────────────────────────
    output_path = write_parquet(
        df=laps,
        key=key,
        data_type=DataType.LAPS,
        base_dir=processed_dir,
        overwrite=overwrite,
    )
    report.output_path = output_path
    report.clean_row_count = len(laps)
    report.retention_pct = (
        round(report.clean_row_count / report.raw_row_count * 100, 2)
        if report.raw_row_count > 0
        else 0.0
    )

    logger.info(
        "Cleaning complete: %s | %d → %d rows (%.1f%% retained) | written: %s",
        key,
        report.raw_row_count,
        report.clean_row_count,
        report.retention_pct,
        output_path,
    )
    return report


def load_clean_laps(
    key: SessionKey,
    processed_base_dir: Path | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Read the Silver-layer cleaned laps Parquet for a session.

    Convenience wrapper used by feature engineering and EDA notebooks so
    they do not need to know about path partitioning conventions.

    Args:
        key: The ``SessionKey`` for the session to read.
        processed_base_dir: Override for the processed data base directory.
        columns: Optional column subset (predicate pushdown via pyarrow).

    Returns:
        Clean laps DataFrame.

    Raises:
        FileNotFoundError: If the Silver Parquet does not exist.
            Run ``run_cleaning_pipeline()`` first.
    """
    settings = get_settings()
    processed_dir = processed_base_dir or settings.data_processed_dir
    return read_parquet(key, DataType.LAPS, base_dir=processed_dir, columns=columns)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _resolve_processed_path(key: SessionKey, processed_dir: Path) -> Path:
    """Compute the Silver-layer Parquet path without creating directories.

    Args:
        key: Session key.
        processed_dir: Base directory for the Silver layer.

    Returns:
        The resolved Path (may or may not exist).
    """
    from f1_predictions.ingestion.parquet_writer import resolve_parquet_path

    return resolve_parquet_path(key, DataType.LAPS, base_dir=processed_dir)
