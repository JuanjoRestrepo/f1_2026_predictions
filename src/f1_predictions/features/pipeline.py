"""Feature engineering pipeline orchestrator for f1_predictions.

Entry point for the Gold-layer feature matrix construction.
Orchestrates: rolling pace → tyre degradation → grid features → OHE encoding.

Output contract:
    The Gold-layer DataFrame written by this module is the direct input to
    the modeling stage. Every column in the output is either:
        - A numeric feature (float32/float64/Int8) ready for XGBoost.
        - A metadata column (Season, RoundNumber, Driver) for joins/reporting.

    No Timedelta, string categorical, or object-dtype columns are permitted
    in the Gold-layer output. The encoder step enforces this.

Idempotency:
    ``run_feature_pipeline()`` checks for an existing Gold Parquet before
    re-computing. Pass ``overwrite=True`` to force recomputation.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from f1_predictions.cleaning.pipeline import load_clean_laps
from f1_predictions.features.encoding import CategoricalFeatureEncoder
from f1_predictions.features.rolling_pace import (
    add_lap_delta_to_fastest,
    add_rolling_pace_features,
)
from f1_predictions.features.tyre_degradation import (
    add_normalised_tyre_life,
    add_tyre_degradation_slope,
)
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
class FeatureReport:
    """Summary of the feature engineering run for one session.

    Attributes:
        key: Session identifier.
        input_row_count: Rows from the Silver layer.
        output_row_count: Rows in the Gold-layer feature matrix.
        input_col_count: Column count before feature engineering.
        output_col_count: Column count after feature engineering.
        ohe_feature_count: Number of OHE columns added.
        output_path: Path to the written Gold Parquet file.
        skipped: True if an existing Gold file was returned without recompute.
    """

    key: SessionKey
    input_row_count: int = 0
    output_row_count: int = 0
    input_col_count: int = 0
    output_col_count: int = 0
    ohe_feature_count: int = 0
    output_path: Path | None = None
    skipped: bool = False


# ── Public API ────────────────────────────────────────────────────────────────

def run_feature_pipeline(
    key: SessionKey,
    encoder: CategoricalFeatureEncoder | None = None,
    overwrite: bool = False,
    processed_base_dir: Path | None = None,
    outputs_base_dir: Path | None = None,
) -> tuple[pd.DataFrame, FeatureReport]:
    """Build the Gold-layer feature matrix for one session.

    Sequence:
        1. Load Silver-layer clean laps from ``data/processed/``.
        2. Add rolling pace features (short/long window + delta).
        3. Add lap delta to driver's fastest lap.
        4. Add tyre degradation OLS slope and normalised tyre life.
        5. Add grid position binary features.
        6. Apply OHE encoding (Compound, EventName, Team).
        7. Write Gold-layer Parquet to ``data/outputs/``.

    Args:
        key: Session identifier.
        encoder: A pre-fitted ``CategoricalFeatureEncoder``. When ``None``,
            a new encoder is fitted on this session's data — appropriate for
            single-session runs and notebooks. For training a multi-session
            model, fit the encoder once on the full training set and pass it
            here to ensure consistent vocabulary across sessions.
        overwrite: If ``True``, recompute even if Gold Parquet exists.
        processed_base_dir: Override for Silver layer base directory.
        outputs_base_dir: Override for Gold layer base directory.

    Returns:
        A tuple of:
            - The Gold-layer feature DataFrame.
            - A ``FeatureReport`` summarising the run.

    Raises:
        FileNotFoundError: If the Silver-layer Parquet does not exist.
            Run the cleaning stage first.

    Example::

        key = SessionKey(2025, 1, "R", "Bahrain Grand Prix")
        features_df, report = run_feature_pipeline(key)
        print(f"Feature matrix: {features_df.shape}")
        print(f"Written to: {report.output_path}")
    """
    settings = get_settings()
    processed_dir = processed_base_dir or settings.data_processed_dir
    outputs_dir = outputs_base_dir or settings.data_outputs_dir

    report = FeatureReport(key=key)

    # ── Idempotency check ─────────────────────────────────────────────────
    gold_path = _resolve_gold_path(key, outputs_dir)
    if gold_path.exists() and not overwrite:
        logger.info(
            "Gold Parquet already exists, skipping feature pipeline "
            "(overwrite=False): %s",
            gold_path,
        )
        existing = read_parquet(key, DataType.LAPS, base_dir=outputs_dir)
        report.skipped = True
        report.output_path = gold_path
        report.output_row_count = len(existing)
        return existing, report

    # ── Step 1: Load Silver layer ─────────────────────────────────────────
    logger.info("Feature pipeline starting: %s", key)
    df = load_clean_laps(key, processed_base_dir=processed_dir)
    report.input_row_count = len(df)
    report.input_col_count = len(df.columns)
    logger.info("Silver laps loaded: %d rows x %d cols", len(df), len(df.columns))

    # ── Step 2: Rolling pace ──────────────────────────────────────────────
    logger.info("Step 2/6 — Rolling pace features")
    df = add_rolling_pace_features(df)
    df = add_lap_delta_to_fastest(df)

    # ── Step 3: Tyre features ─────────────────────────────────────────────
    logger.info("Step 3/6 — Tyre degradation features")
    df = add_tyre_degradation_slope(df)
    df = add_normalised_tyre_life(df)

    # ── Step 4: Grid position ─────────────────────────────────────────────
    # GridPosition is on results, not laps. Apply only if column is present.
    if "GridPosition" in df.columns:
        logger.info("Step 4/6 — Grid position features")
        from f1_predictions.features.encoding import add_grid_position_features
        df = add_grid_position_features(df)
    else:
        logger.info(
            "Step 4/6 — GridPosition not found in laps DataFrame "
            "(join results before feature pipeline if needed). Skipping."
        )

    # ── Step 5: OHE encoding ──────────────────────────────────────────────
    logger.info("Step 5/6 — Categorical OHE encoding")
    # Only encode columns that are actually present in this session's data.
    from f1_predictions.features.encoding import DEFAULT_OHE_COLUMNS
    available_ohe_cols = [c for c in DEFAULT_OHE_COLUMNS if c in df.columns]

    if available_ohe_cols:
        if encoder is None:
            encoder = CategoricalFeatureEncoder(columns=available_ohe_cols)
            df = encoder.fit_transform(df)
        else:
            df = encoder.transform(df)
        report.ohe_feature_count = encoder.n_features_out
    else:
        logger.warning("No OHE columns found in DataFrame — encoding step skipped.")

    # ── Step 6: Write Gold Parquet ────────────────────────────────────────
    logger.info("Step 6/6 — Writing Gold Parquet")
    output_path = write_parquet(
        df=df,
        key=key,
        data_type=DataType.LAPS,
        base_dir=outputs_dir,
        overwrite=overwrite,
    )

    report.output_row_count = len(df)
    report.output_col_count = len(df.columns)
    report.output_path = output_path

    logger.info(
        "Feature pipeline complete: %s | %d x %d → %d x %d | OHE cols: %d | %s",
        key,
        report.input_row_count, report.input_col_count,
        report.output_row_count, report.output_col_count,
        report.ohe_feature_count,
        output_path,
    )
    return df, report


def load_feature_matrix(
    key: SessionKey,
    outputs_base_dir: Path | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Read the Gold-layer feature matrix for a session.

    Convenience reader for modeling notebooks so they do not need to
    know about path partitioning conventions.

    Args:
        key: Session identifier.
        outputs_base_dir: Override for Gold layer base directory.
        columns: Optional column subset for predicate pushdown.

    Returns:
        Gold-layer feature DataFrame.

    Raises:
        FileNotFoundError: If Gold Parquet does not exist.
    """
    settings = get_settings()
    outputs_dir = outputs_base_dir or settings.data_outputs_dir
    return read_parquet(key, DataType.LAPS, base_dir=outputs_dir, columns=columns)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_gold_path(key: SessionKey, outputs_dir: Path) -> Path:
    """Compute the Gold-layer Parquet path without creating directories.

    Args:
        key: Session key.
        outputs_dir: Gold layer base directory.

    Returns:
        Resolved Path (may or may not exist).
    """
    from f1_predictions.ingestion.parquet_writer import resolve_parquet_path
    return resolve_parquet_path(key, DataType.LAPS, base_dir=outputs_dir)
