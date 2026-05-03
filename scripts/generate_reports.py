"""Post-race report generator: train models and export all artifacts.

Usage::

    uv run python scripts/generate_reports.py --train-years 2022 2023 2024 --test-year 2024
    uv run python scripts/generate_reports.py --train-years 2022 2023 --test-year 2024 --no-shap

Pipeline stages executed:
    1. Discover and concatenate all Gold-layer Parquet files.
    2. Chronological train/test split by season.
    3. Train XGBoost and LightGBM regressors.
    4. Evaluate (MAE, RMSE) and persist metrics to JSON.
    5. Generate predicted-vs-actual scatter plot (fig_01).
    6. Generate Feature Importance bar charts for both models (fig_02, fig_03).
    7. Optionally: SHAP summary and bar plots (fig_07, fig_08).
    8. Render a Jinja2 HTML report linking all figures.

All outputs go to the directory defined by F1_REPORTS_DIR (default: reports/).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from f1_predictions.models import (
    F1PaceRegressor,
    LightGBMPaceRegressor,
    RegressionMetrics,
    chronological_split,
    prepare_feature_matrix,
)
from f1_predictions.models.explainability import save_tree_shap_artifacts
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

# Use non-interactive backend: prevents display errors in headless/CI environments.
matplotlib.use("Agg")

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FIGURE_DPI: int = 150
SCATTER_ALPHA: float = 0.45
SCATTER_COLOR: str = "#E8002D"  # F1 red
BAR_COLOR_XGB: str = "#1E88E5"
BAR_COLOR_LGB: str = "#43A047"
TOP_N_FEATURES: int = 20


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_gold_dataframe(data_outputs_dir: Path) -> pd.DataFrame:
    """Discover and concatenate all Gold-layer Parquet files.

    Args:
        data_outputs_dir: Root directory of the Gold-layer Parquet files,
            structured as ``<data_outputs_dir>/<season>/<round>/gold_laps.parquet``.

    Returns:
        Concatenated DataFrame from all discovered files.

    Raises:
        FileNotFoundError: If no Parquet files are found under the directory.
        ValueError: If the concatenated DataFrame is empty.
    """
    parquet_files = sorted(data_outputs_dir.rglob("*.parquet"))
    if not parquet_files:
        msg = (
            f"No Parquet files found under '{data_outputs_dir}'. "
            "Run `scripts/ingest_season.py` first to populate the Gold layer."
        )
        raise FileNotFoundError(msg)

    logger.info("Discovered %d Gold Parquet files.", len(parquet_files))
    frames = [pd.read_parquet(p) for p in parquet_files]
    df = pd.concat(frames, ignore_index=True)

    if df.empty:
        msg = "Concatenated Gold DataFrame is empty. Check the Parquet files."
        raise ValueError(msg)

    logger.info("Loaded %d rows x %d columns from Gold layer.", *df.shape)
    return df


# ---------------------------------------------------------------------------
# Figure generators
# ---------------------------------------------------------------------------


def _save_and_close(path: Path) -> None:
    """Save the current matplotlib figure and close it cleanly."""
    plt.savefig(path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close()
    logger.info("Saved figure: %s", path)


def plot_predicted_vs_actual(
    y_true: pd.Series,
    y_pred_xgb: np.ndarray,
    y_pred_lgb: np.ndarray,
    metrics_xgb: RegressionMetrics,
    metrics_lgb: RegressionMetrics,
    reports_dir: Path,
) -> Path:
    """Scatter plot of predicted vs actual lap times for both models.

    Args:
        y_true: Ground-truth lap times in seconds.
        y_pred_xgb: XGBoost predictions.
        y_pred_lgb: LightGBM predictions.
        metrics_xgb: Evaluation metrics for XGBoost.
        metrics_lgb: Evaluation metrics for LightGBM.
        reports_dir: Directory to write the figure.

    Returns:
        Path to the saved figure.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    fig.suptitle(
        "Predicted vs Actual Lap Times (Test Season)", fontsize=14, fontweight="bold"
    )

    for ax, y_pred, metrics, label, color in zip(
        axes,
        [y_pred_xgb, y_pred_lgb],
        [metrics_xgb, metrics_lgb],
        ["XGBoost", "LightGBM"],
        [BAR_COLOR_XGB, BAR_COLOR_LGB],
        strict=True,
    ):
        min_val = float(min(y_true.min(), y_pred.min()))
        max_val = float(max(y_true.max(), y_pred.max()))

        ax.scatter(y_true, y_pred, alpha=SCATTER_ALPHA, color=color, s=12, linewidths=0)
        ax.plot(
            [min_val, max_val],
            [min_val, max_val],
            "k--",
            linewidth=1,
            label="Perfect fit",
        )
        ax.set_xlabel("Actual Lap Time (s)", fontsize=11)
        ax.set_ylabel("Predicted Lap Time (s)", fontsize=11)
        ax.set_title(
            f"{label}\nMAE={metrics.mae:.3f}s  RMSE={metrics.rmse:.3f}s",
            fontsize=11,
        )
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = reports_dir / "fig_01_predicted_vs_actual.png"
    _save_and_close(out_path)
    return out_path


def plot_feature_importance(
    feature_names: list[str],
    importances: np.ndarray,
    model_label: str,
    filename: str,
    color: str,
    reports_dir: Path,
) -> Path:
    """Horizontal bar chart of the top-N most important features.

    Args:
        feature_names: Ordered feature column names.
        importances: Raw importance scores from the fitted model.
        model_label: Display name of the model (e.g. ``"XGBoost"``).
        filename: Output filename (e.g. ``"fig_02_importance_xgb.png"``).
        color: Bar fill colour.
        reports_dir: Directory to write the figure.

    Returns:
        Path to the saved figure.
    """
    importance_series = pd.Series(importances, index=feature_names)
    top = importance_series.nlargest(TOP_N_FEATURES).sort_values()

    _fig, ax = plt.subplots(figsize=(10, 6))
    top.plot.barh(ax=ax, color=color, alpha=0.85)
    ax.set_xlabel("Feature Importance Score", fontsize=11)
    ax.set_title(
        f"Top-{TOP_N_FEATURES} Feature Importances — {model_label}",
        fontsize=13,
        fontweight="bold",
    )
    ax.grid(True, axis="x", alpha=0.3)
    plt.tight_layout()

    out_path = reports_dir / filename
    _save_and_close(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Metrics persistence
# ---------------------------------------------------------------------------


def save_metrics_json(
    metrics_xgb: RegressionMetrics,
    metrics_lgb: RegressionMetrics,
    train_years: list[int],
    test_year: int,
    reports_dir: Path,
) -> Path:
    """Persist evaluation metrics to a JSON file for downstream consumption.

    Args:
        metrics_xgb: XGBoost evaluation metrics.
        metrics_lgb: LightGBM evaluation metrics.
        train_years: Seasons used for training.
        test_year: Season used for testing.
        reports_dir: Output directory.

    Returns:
        Path to the saved JSON file.
    """
    payload: dict[str, Any] = {
        "train_years": train_years,
        "test_year": test_year,
        "xgboost": metrics_xgb.as_dict(),
        "lightgbm": metrics_lgb.as_dict(),
    }
    out_path = reports_dir / "metrics.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Metrics saved: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# HTML report rendering
# ---------------------------------------------------------------------------


def render_html_report(
    test_year: int,
    metrics_xgb: RegressionMetrics,
    metrics_lgb: RegressionMetrics,
    train_years: list[int],
    figure_paths: dict[str, Path],
    reports_dir: Path,
    event_filter: str | None = None,
) -> Path:
    """Render the Jinja2 template and save the final HTML report.
    summarising all results.

       Args:
           metrics_xgb: XGBoost evaluation metrics.
           metrics_lgb: LightGBM evaluation metrics.
           train_years: Seasons used for training.
           test_year: Season used for testing.
           figure_paths: Mapping of figure key to saved Path.
           reports_dir: Output directory for the HTML file.
           event_filter: Optional GP event name filtering.

       Returns:
           Path to the rendered HTML report.
    """
    from jinja2 import Environment, FileSystemLoader

    template_dir = Path(__file__).parent.parent / "src" / "f1_predictions" / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("report.html.j2")

    # Build relative paths from reports_dir for self-contained HTML navigation
    rel_figures: dict[str, str] = {key: path.name for key, path in figure_paths.items()}

    html_content = template.render(
        train_years=train_years,
        test_year=test_year,
        metrics_xgb=metrics_xgb.as_dict(),
        metrics_lgb=metrics_lgb.as_dict(),
        figures=rel_figures,
    )

    # Final output path
    if event_filter:
        # This is a GP-specific report
        safe_name = event_filter.replace(" ", "_")
        filename = f"REPORTE_{safe_name}_{test_year}.html"
    else:
        # This is a Season-wide report
        filename = f"REPORTE_GLOBAL_TEMPORADA_{test_year}.html"

    out_path = reports_dir / filename
    out_path.write_text(html_content, encoding="utf-8")
    logger.info("HTML report saved: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_report_pipeline(
    train_years: list[int],
    test_year: int,
    include_shap: bool,
    event_filter: str | None = None,
) -> None:
    """Execute the full report generation pipeline.

    Args:
        train_years: List of seasons to use for model training.
        test_year: Season to use as held-out test set.
        include_shap: Whether to generate SHAP explainability plots.
        event_filter: Optional GP event name to filter the test set.
    """
    settings = get_settings()

    # ── 2. Create versioned output directory (Hierarchical) ──────────────
    reports_root = Path(settings.reports_dir)
    if event_filter:
        safe_event = event_filter.replace(" ", "_")
        reports_dir = reports_root / str(test_year) / safe_event / "results"
    else:
        reports_dir = reports_root / str(test_year)

    reports_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Reports will be saved to: %s", reports_dir)

    # ── 1. Load Gold data ─────────────────────────────────────────────────
    df = load_gold_dataframe(settings.data_outputs_dir)

    # ── 2. Chronological split ────────────────────────────────────────────
    df_train, df_test = chronological_split(df, train_years, test_year)

    if event_filter:
        df_test = df_test[df_test["EventName"] == event_filter].copy()
        if df_test.empty:
            logger.error(
                "No data found for event '%s' in season %d", event_filter, test_year
            )
            raise ValueError(f"Event '{event_filter}' not found in test set.")
        logger.info(
            "Filtering report for event: %s (%d rows)", event_filter, len(df_test)
        )

    logger.info("Train rows: %d  |  Test rows: %d", len(df_train), len(df_test))

    x_train, _y_train = prepare_feature_matrix(df_train)
    x_test, y_test = prepare_feature_matrix(df_test)

    # Align columns: Gold files built per-session may have different one-hot cols
    shared_cols = [c for c in x_train.columns if c in x_test.columns]
    x_train, x_test = x_train[shared_cols], x_test[shared_cols]
    logger.info("Shared feature columns: %d", len(shared_cols))

    # ── 3. Training & Evaluation: XGBoost
    logger.info("Training XGBoost...")
    model_xgb = F1PaceRegressor()
    metrics_xgb_dict = model_xgb.train_evaluate_chronological(
        df, train_years, test_year
    )
    metrics_xgb = RegressionMetrics(
        mae=metrics_xgb_dict["MAE"], rmse=metrics_xgb_dict["RMSE"]
    )
    y_pred_xgb = model_xgb.predict(df_test)

    # 4. Training & Evaluation: LightGBM
    logger.info("Training LightGBM...")
    model_lgb = LightGBMPaceRegressor()
    metrics_lgb_dict = model_lgb.train_evaluate_chronological(
        df, train_years, test_year
    )
    metrics_lgb = RegressionMetrics(
        mae=metrics_lgb_dict["MAE"], rmse=metrics_lgb_dict["RMSE"]
    )
    y_pred_lgb = model_lgb.predict(df_test)

    # ── 5. Save metrics JSON ──────────────────────────────────────────────
    save_metrics_json(metrics_xgb, metrics_lgb, train_years, test_year, reports_dir)

    # ── 6. Generate figures ───────────────────────────────────────────────
    figure_paths: dict[str, Path] = {}

    figure_paths["predicted_vs_actual"] = plot_predicted_vs_actual(
        y_test, y_pred_xgb, y_pred_lgb, metrics_xgb, metrics_lgb, reports_dir
    )

    import xgboost as xgb
    from lightgbm import LGBMRegressor

    xgb_est = cast(xgb.XGBRegressor, model_xgb.model)
    lgb_est = cast(LGBMRegressor, model_lgb.model)

    xgb_importances: np.ndarray = xgb_est.feature_importances_
    figure_paths["importance_xgb"] = plot_feature_importance(
        shared_cols,
        xgb_importances,
        "XGBoost",
        "fig_02_importance_xgb.png",
        BAR_COLOR_XGB,
        reports_dir,
    )

    lgb_importances: np.ndarray = lgb_est.feature_importances_
    figure_paths["importance_lgb"] = plot_feature_importance(
        shared_cols,
        lgb_importances,
        "LightGBM",
        "fig_03_importance_lgb.png",
        BAR_COLOR_LGB,
        reports_dir,
    )

    # ── 7. SHAP (optional) ────────────────────────────────────────────────
    if include_shap:
        logger.info("Generating SHAP plots (LightGBM)...")
        shap_paths = save_tree_shap_artifacts(lgb_est, x_test, reports_dir)
        figure_paths.update(shap_paths)
    else:
        logger.info("SHAP skipped (use --shap to enable).")

    # ── 7. Render HTML report ─────────────────────────────────────────────
    html_path = render_html_report(
        test_year,
        metrics_xgb,
        metrics_lgb,
        train_years,
        figure_paths,
        reports_dir,
        event_filter=event_filter,
    )

    logger.info("=" * 60)
    logger.info("Report generation complete.")
    logger.info("HTML report: %s", html_path)
    logger.info("XGBoost  — MAE: %.3fs  RMSE: %.3fs", metrics_xgb.mae, metrics_xgb.rmse)
    logger.info("LightGBM — MAE: %.3fs  RMSE: %.3fs", metrics_lgb.mae, metrics_lgb.rmse)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the report generator."""
    parser = argparse.ArgumentParser(
        description="Train F1 pace models and export all report artifacts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--train-years",
        nargs="+",
        type=int,
        required=True,
        help="Seasons to use for training (e.g. --train-years 2022 2023 2024).",
    )
    parser.add_argument(
        "--test-year",
        type=int,
        required=True,
        help="Season to use as the held-out test set.",
    )
    parser.add_argument(
        "--shap",
        action="store_true",
        dest="include_shap",
        help="Generate SHAP summary and bar plots (requires shap package).",
    )
    parser.add_argument(
        "--event",
        type=str,
        help="Specific GP event name to filter and report on (e.g., 'Miami Grand Prix').",
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
        "Starting report pipeline: train=%s  test=%d  shap=%s",
        args.train_years,
        args.test_year,
        args.include_shap,
    )

    try:
        run_report_pipeline(
            train_years=args.train_years,
            test_year=args.test_year,
            include_shap=args.include_shap,
            event_filter=args.event,
        )
    except (FileNotFoundError, ValueError):
        logger.exception("Pipeline failed.")
        sys.exit(1)

    sys.exit(0)
