"""Refresh the serving artifact (XGBoost joblib) from the current Gold layer.

The FastAPI container loads ``data/outputs/models/xgb_pace_model.joblib`` at
startup and never retrains. That makes the file a snapshot, and a stale
snapshot serves a model whose feature set no longer matches the pipeline. This
script makes the refresh explicit and reproducible, and writes a sidecar with
the provenance the binary cannot carry.

Usage::

    uv run python scripts/refresh_serving_artifact.py --predict-year 2026
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

# Running a file inside ``scripts/`` puts that directory on sys.path, not the
# repository root; make the package import work either way.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.predict_season import load_gold_by_season, train_models  # noqa: E402

logger = get_logger(__name__)


def _git_sha() -> str:
    """Return the current commit, or ``unknown`` outside a git checkout."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return "unknown"


def refresh(predict_year: int, train_years: list[int]) -> Path:
    """Train the product model on ``train_years`` and persist the artifact.

    Args:
        predict_year: Season whose Gold layer defines the serving feature set.
        train_years: Seasons used for fitting.

    Returns:
        Path of the written joblib.

    Raises:
        ValueError: If ``predict_year`` is also a training year.
    """
    if predict_year in train_years:
        msg = f"predict_year {predict_year} must not appear in train_years."
        raise ValueError(msg)

    settings = get_settings()
    df_all, df_predict = load_gold_by_season(settings.data_outputs_dir, predict_year)

    xgb_model, _lgb_model, _stack_model = train_models(
        df_all, train_years, predict_year, settings.random_seed, tune_trials=0
    )

    model_path = Path(settings.data_outputs_dir) / "models" / "xgb_pace_model.joblib"
    xgb_model.save(model_path)

    metadata = {
        "trained_at_utc": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "predict_year": predict_year,
        "train_years": train_years,
        "feature_count": len(xgb_model.features),
        "features": list(xgb_model.features),
        "gold_rows": int(len(df_all)),
        "predict_rows": int(len(df_predict)),
        "random_seed": settings.random_seed,
    }
    metadata_path = model_path.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    logger.info(
        "Serving artifact refreshed: %s (%d features, trained on %s)",
        model_path,
        len(xgb_model.features),
        train_years,
    )
    return model_path


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predict-year", type=int, default=2026)
    parser.add_argument(
        "--train-years",
        nargs="+",
        type=int,
        default=[2022, 2023, 2024, 2025],
    )
    return parser.parse_args()


if __name__ == "__main__":
    configure_root_pipeline_logger("INFO")
    args = parse_args()
    refresh(args.predict_year, args.train_years)
