"""Explainability helpers for tree-based F1 models."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)


def save_tree_shap_artifacts(
    model: object,
    x_test: pd.DataFrame,
    reports_dir: Path,
    summary_filename: str = "fig_07_shap_summary.png",
    bar_filename: str = "fig_08_shap_bar.png",
    explainer_factory: Callable[[object], object] | None = None,
    summary_plot_fn: Callable[..., None] | None = None,
    bar_plot_fn: Callable[..., None] | None = None,
    savefig_fn: Callable[[Path], None] | None = None,
    close_fn: Callable[[], None] | None = None,
) -> dict[str, Path]:
    """Render and persist SHAP summary and bar plots for a tree model.

    Args:
        model: Fitted tree-based estimator compatible with SHAP explainers.
        x_test: Feature matrix to explain.
        reports_dir: Output directory for the generated artifacts.
        summary_filename: Filename for the beeswarm summary plot.
        bar_filename: Filename for the global mean absolute SHAP bar plot.
        explainer_factory: Optional explainer constructor for testing.
        summary_plot_fn: Optional replacement for ``shap.summary_plot``.
        bar_plot_fn: Optional replacement for ``shap.plots.bar``.
        savefig_fn: Optional replacement for ``matplotlib.pyplot.savefig``.
        close_fn: Optional replacement for ``matplotlib.pyplot.close``.

    Returns:
        Dictionary mapping artifact names to the saved paths.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)

    if explainer_factory is None or summary_plot_fn is None or bar_plot_fn is None:
        import shap

        explainer_factory = explainer_factory or shap.TreeExplainer
        summary_plot_fn = summary_plot_fn or shap.summary_plot
        bar_plot_fn = bar_plot_fn or shap.plots.bar
    savefig_fn = savefig_fn or (lambda path: plt.savefig(path, bbox_inches="tight"))
    close_fn = close_fn or plt.close

    explainer = explainer_factory(model)
    shap_values = explainer.shap_values(x_test)

    summary_path = reports_dir / summary_filename
    bar_path = reports_dir / bar_filename

    plt.figure(figsize=(10, 8))
    summary_plot_fn(shap_values, x_test, show=False)
    plt.title("SHAP Summary Plot - Feature Impact Directionality", fontsize=14, pad=20)
    savefig_fn(summary_path)
    close_fn()

    plt.figure(figsize=(10, 6))
    bar_plot_fn(explainer(x_test), show=False)
    plt.title("Mean |SHAP Value| (Average Impact)", fontsize=14)
    savefig_fn(bar_path)
    close_fn()

    logger.info("Saved SHAP artifacts: %s, %s", summary_path, bar_path)
    return {"summary": summary_path, "bar": bar_path}
