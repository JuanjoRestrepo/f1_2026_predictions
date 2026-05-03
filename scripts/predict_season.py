"""Season prediction script: apply a trained model to an unseen season.

Trains XGBoost and LightGBM on ``--train-years`` (e.g. 2022-2024), then
produces per-lap predictions for every Gold-layer Parquet found under
``--predict-year`` (e.g. 2025 or 2026).

Usage::

    # Predict 2025 season using 2022-2024 training data
    uv run python scripts/predict_season.py \\
        --train-years 2022 2023 2024 --predict-year 2025

    # Predict 2026 (once data is available)
    uv run python scripts/predict_season.py \\
        --train-years 2022 2023 2024 2025 --predict-year 2026

Output files (written to F1_REPORTS_DIR / predictions/)::

    predictions_xgb_<predict_year>.parquet   Per-lap XGBoost predictions
    predictions_lgb_<predict_year>.parquet   Per-lap LightGBM predictions
    standings_xgb_<predict_year>.csv         Driver standings by predicted pace
    standings_lgb_<predict_year>.csv         Driver standings by predicted pace
    predictions_summary_<predict_year>.json  Metadata + top-5 drivers

Design rationale:
    - Trains on seasons with known outcomes (2022-2024) — pure historical data.
    - Predicts on the target season's Gold layer, which may be partially populated
      (mid-season) or fully populated (end-of-season post-processing).
    - Chronological split: prediction year must NOT appear in train_years to
      prevent data leakage.
    - Feature alignment: only shared columns between train and predict matrices
      are used; new OHE categories in the predict year are silently dropped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import xgboost as xgb
from lightgbm import LGBMRegressor

from f1_predictions.models import (
    F1PaceRegressor,
    LightGBMPaceRegressor,
    prepare_feature_matrix,
)
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Metadata columns to carry through to the predictions output for reporting.
# These are NOT fed to the model — they're preserved from the Gold layer for
# joining predictions back to race results.
METADATA_COLS: list[str] = [
    "Driver",
    "Team",
    "EventName",
    "Season",
    "RoundNumber",
    "LapNumber",
]


# ---------------------------------------------------------------------------
# Data utilities
# ---------------------------------------------------------------------------


def load_gold_by_season(
    data_outputs_dir: Path,
    season: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and concatenate all Gold Parquet files for a specific season.

    Args:
        data_outputs_dir: Root directory of Gold-layer outputs.
        season: Target season year.

    Returns:
        Concatenated DataFrame filtered to ``season``.

    Raises:
        FileNotFoundError: If no Parquet files are found for the season.
        ValueError: If the season slice is empty after filtering.
    """
    all_parquets = sorted(data_outputs_dir.rglob("*.parquet"))
    if not all_parquets:
        msg = (
            f"No Parquet files found under '{data_outputs_dir}'. "
            "Run `scripts/ingest_season.py` first."
        )
        raise FileNotFoundError(msg)

    frames = [pd.read_parquet(p) for p in all_parquets]
    df_all = pd.concat(frames, ignore_index=True)

    if "Season" not in df_all.columns:
        msg = "Gold DataFrame missing required 'Season' column."
        raise ValueError(msg)

    df_season = df_all[df_all["Season"] == season].copy()
    if df_season.empty:
        msg = (
            f"No rows found for season {season} in the Gold layer. "
            f"Available seasons: {sorted(df_all['Season'].unique().tolist())}. "
            "Ingest the season first with `scripts/ingest_season.py --year {season}`."
        )
        raise ValueError(msg)

    logger.info(
        "Loaded %d Gold rows for season %d from %d total rows.",
        len(df_season),
        season,
        len(df_all),
    )
    return df_all, df_season


def extract_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Extract metadata columns present in the DataFrame.

    Args:
        df: Gold-layer DataFrame.

    Returns:
        DataFrame with only the metadata columns that exist.
    """
    present = [c for c in METADATA_COLS if c in df.columns]
    return df[present].copy()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train_models(
    df_all: pd.DataFrame,
    train_years: list[int],
    predict_year: int,
    random_seed: int,
) -> tuple[F1PaceRegressor, LightGBMPaceRegressor]:
    """Train XGBoost and LightGBM on the specified training seasons.

    Uses chronological_split to isolate training data. The predict_year data
    is used as the held-out evaluation set during training (early stopping
    signals), but the trained model is applied to the full predict_year Gold
    layer afterwards.

    Args:
        df_all: Full multi-season Gold DataFrame.
        train_years: Seasons used to train (e.g. [2022, 2023, 2024]).
        predict_year: Season being predicted (used as eval set).
        random_seed: Reproducibility seed.

    Returns:
        Tuple of (trained XGBoost regressor, trained LightGBM regressor).

    Raises:
        ValueError: If predict_year appears in train_years (data leakage guard).
    """
    if predict_year in train_years:
        msg = (
            f"predict_year={predict_year} must NOT appear in train_years={train_years}. "
            "This would constitute target-season data leakage."
        )
        raise ValueError(msg)

    logger.info("Training XGBoost on seasons %s...", train_years)
    xgb_model = F1PaceRegressor(random_state=random_seed)
    xgb_model.train_evaluate_chronological(df_all, train_years, predict_year)

    logger.info("Training LightGBM on seasons %s...", train_years)
    lgb_model = LightGBMPaceRegressor(random_state=random_seed)
    lgb_model.train_evaluate_chronological(df_all, train_years, predict_year)

    return xgb_model, lgb_model


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def predict_season(
    xgb_model: F1PaceRegressor,
    lgb_model: LightGBMPaceRegressor,
    df_predict: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Apply trained models to the target season and return predictions.

    Aligns feature columns between the trained models and the predict DataFrame.
    Columns present in training but absent in prediction are filled with NaN.
    Columns present in prediction but absent in training are silently dropped
    (e.g. new OHE categories from a new circuit on the 2026 calendar).

    Args:
        xgb_model: Fitted XGBoost regressor.
        lgb_model: Fitted LightGBM regressor.
        df_predict: Gold-layer DataFrame for the target season.

    Returns:
        Tuple of:
            - XGBoost predictions (np.ndarray, seconds per lap).
            - LightGBM predictions (np.ndarray, seconds per lap).
            - Feature matrix used for inference (for diagnostics).

    Raises:
        RuntimeError: If models have not been trained (no stored feature list).
    """
    if not xgb_model.features:
        msg = "XGBoost model must be trained before predict_season() is called."
        raise RuntimeError(msg)

    x_predict, _ = prepare_feature_matrix(df_predict, require_target=False)

    # Align to training feature set: add missing cols as NaN, drop extras.
    x_aligned = x_predict.reindex(columns=xgb_model.features, fill_value=np.nan)

    xgb_est = cast(xgb.XGBRegressor, xgb_model.model)
    lgb_est = cast(LGBMRegressor, lgb_model.model)

    y_pred_xgb: np.ndarray = xgb_est.predict(x_aligned)
    y_pred_lgb: np.ndarray = lgb_est.predict(x_aligned)

    logger.info(
        "Inference complete: %d laps | XGB mean=%.3fs | LGB mean=%.3fs",
        len(x_aligned),
        float(y_pred_xgb.mean()),
        float(y_pred_lgb.mean()),
    )
    return y_pred_xgb, y_pred_lgb, x_aligned


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------


def build_predictions_df(
    metadata: pd.DataFrame,
    y_pred_xgb: np.ndarray,
    y_pred_lgb: np.ndarray,
) -> pd.DataFrame:
    """Build a unified predictions DataFrame with metadata columns.

    Args:
        metadata: Metadata columns (Driver, Team, EventName, …).
        y_pred_xgb: XGBoost lap-time predictions in seconds.
        y_pred_lgb: LightGBM lap-time predictions in seconds.

    Returns:
        DataFrame with metadata + prediction columns.
    """
    result = metadata.copy().reset_index(drop=True)
    result["predicted_laptime_xgb_s"] = y_pred_xgb
    result["predicted_laptime_lgb_s"] = y_pred_lgb
    result["ensemble_laptime_s"] = (y_pred_xgb + y_pred_lgb) / 2.0
    return result


def build_driver_standings(
    predictions_df: pd.DataFrame,
    model_col: str,
) -> pd.DataFrame:
    """Aggregate per-lap predictions into a driver pace ranking.

    Uses median predicted lap time as the ranking metric — more robust
    than mean to outlier laps (safety car, pit laps, installation laps).

    Args:
        predictions_df: Per-lap predictions DataFrame.
        model_col: Column name for the model's predictions.

    Returns:
        Driver standings DataFrame sorted by median predicted pace (fastest first).
    """
    group_cols = ["Driver", "Team"] if "Team" in predictions_df.columns else ["Driver"]
    standings = (
        predictions_df.groupby(group_cols)[model_col]
        .agg(
            median_predicted_s="median",
            mean_predicted_s="mean",
            lap_count="count",
            std_predicted_s="std",
        )
        .reset_index()
        .sort_values("median_predicted_s")
        .reset_index(drop=True)
    )
    standings.insert(0, "rank", standings.index + 1)
    return standings


def save_outputs(
    predictions_df: pd.DataFrame,
    predict_year: int,
    train_years: list[int],
    output_dir: Path,
) -> dict[str, Path]:
    """Persist all prediction artifacts to disk.

    Args:
        predictions_df: Full per-lap predictions DataFrame.
        predict_year: Season being predicted.
        train_years: Seasons used for training.
        output_dir: Root output directory (under F1_REPORTS_DIR/predictions/).

    Returns:
        Dictionary mapping artifact name to saved Path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}

    # Per-lap prediction Parquets (full fidelity, for downstream analysis)
    xgb_parquet = output_dir / f"predictions_xgb_{predict_year}.parquet"
    lgb_parquet = output_dir / f"predictions_lgb_{predict_year}.parquet"
    predictions_df.to_parquet(xgb_parquet, index=False)
    predictions_df.to_parquet(lgb_parquet, index=False)
    saved["predictions_xgb_parquet"] = xgb_parquet
    saved["predictions_lgb_parquet"] = lgb_parquet
    logger.info("Saved prediction Parquets: %s, %s", xgb_parquet, lgb_parquet)

    # Driver standings CSVs
    for model_key, col in [
        ("xgb", "predicted_laptime_xgb_s"),
        ("lgb", "predicted_laptime_lgb_s"),
    ]:
        standings = build_driver_standings(predictions_df, col)
        standings_path = output_dir / f"standings_{model_key}_{predict_year}.csv"
        standings.to_csv(standings_path, index=False)
        saved[f"standings_{model_key}"] = standings_path
        logger.info("Saved %s standings: %s", model_key.upper(), standings_path)

    # Summary JSON with top-5 drivers
    xgb_standings = build_driver_standings(predictions_df, "predicted_laptime_xgb_s")
    lgb_standings = build_driver_standings(predictions_df, "predicted_laptime_lgb_s")

    summary: dict[str, Any] = {
        "predict_year": predict_year,
        "train_years": train_years,
        "total_laps_predicted": len(predictions_df),
        "top5_drivers_xgb": xgb_standings.head(5)[
            ["rank", "Driver", "median_predicted_s"]
        ].to_dict(orient="records"),
        "top5_drivers_lgb": lgb_standings.head(5)[
            ["rank", "Driver", "median_predicted_s"]
        ].to_dict(orient="records"),
    }
    summary_path = output_dir / f"predictions_summary_{predict_year}.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    saved["summary_json"] = summary_path
    logger.info("Saved summary JSON: %s", summary_path)

    return saved


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_prediction_pipeline(
    train_years: list[int],
    predict_year: int,
) -> None:
    """Execute the full prediction pipeline.

    Trains on historical Gold data, applies to target season, and saves outputs.

    Args:
        train_years: Seasons used for model training.
        predict_year: Season to generate predictions for.
    """
    settings = get_settings()
    output_dir = settings.reports_dir / "predictions"

    # ── 1. Load data ───────────────────────────────────────────────────────
    df_all: pd.DataFrame
    df_predict: pd.DataFrame
    df_all, df_predict = load_gold_by_season(settings.data_outputs_dir, predict_year)

    available_seasons = sorted(df_all["Season"].unique().tolist())
    missing_train = [y for y in train_years if y not in available_seasons]
    if missing_train:
        logger.warning(
            "Training years %s not found in Gold layer. "
            "Available: %s. Proceeding with available years.",
            missing_train,
            available_seasons,
        )
        train_years = [y for y in train_years if y in available_seasons]

    if not train_years:
        msg = "No training seasons available in the Gold layer. Ingest data first."
        raise ValueError(msg)

    # ── 2. Train ───────────────────────────────────────────────────────────
    xgb_model, lgb_model = train_models(
        df_all, train_years, predict_year, settings.random_seed
    )

    # ── 3. Predict ─────────────────────────────────────────────────────────
    y_pred_xgb, y_pred_lgb, _ = predict_season(xgb_model, lgb_model, df_predict)

    # ── 4. Build & save outputs ────────────────────────────────────────────
    metadata = extract_metadata(df_predict)
    predictions_df = build_predictions_df(metadata, y_pred_xgb, y_pred_lgb)
    saved = save_outputs(predictions_df, predict_year, train_years, output_dir)

    # ── 5. Print standings to console ─────────────────────────────────────
    xgb_standings = build_driver_standings(predictions_df, "predicted_laptime_xgb_s")
    logger.info("=" * 60)
    logger.info("PREDICTED DRIVER STANDINGS — Season %d (XGBoost)", predict_year)
    logger.info("(Ranked by median predicted lap time — lower = faster)")
    logger.info("=" * 60)
    for _, row in xgb_standings.head(10).iterrows():
        driver = row.get("Driver", "Unknown")
        team = row.get("Team", "")
        team_str = f" ({team})" if team else ""
        logger.info(
            "  P%02d  %-20s%s  %.3fs",
            int(row["rank"]),
            str(driver),
            team_str,
            float(row["median_predicted_s"]),
        )
    logger.info("=" * 60)
    logger.info("Artifacts saved:")
    for name, path in saved.items():
        logger.info("  %s → %s", name, path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the prediction script."""
    parser = argparse.ArgumentParser(
        description="Train on historical F1 seasons and predict an unseen season.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--train-years",
        nargs="+",
        type=int,
        required=True,
        help="Seasons to use for model training (e.g. --train-years 2022 2023 2024).",
    )
    parser.add_argument(
        "--predict-year",
        type=int,
        required=True,
        help="Season to predict (must NOT be in --train-years).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    configure_root_pipeline_logger(level=args.log_level)

    logger.info(
        "F1 Prediction Pipeline | Train=%s → Predict=%d",
        args.train_years,
        args.predict_year,
    )

    try:
        run_prediction_pipeline(
            train_years=args.train_years,
            predict_year=args.predict_year,
        )
    except (FileNotFoundError, ValueError):
        logger.exception("Prediction pipeline failed.")
        sys.exit(1)

    sys.exit(0)
