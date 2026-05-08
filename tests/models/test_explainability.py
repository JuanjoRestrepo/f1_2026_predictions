"""Tests for SHAP artifact generation."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from f1_predictions.models.explainability import (
    get_top_shap_features,
    save_tree_shap_artifacts,
)
import xgboost as xgb


def test_save_tree_shap_artifacts_creates_pngs() -> None:
    """save_tree_shap_artifacts should persist both SHAP figures."""

    rng = np.random.default_rng(42)
    x = pd.DataFrame(
        {
            "roll_laptime_3": rng.normal(90.0, 1.0, 6),
            "tyre_life_norm": rng.uniform(0.0, 1.0, 6),
            "TrackTemp_mean": rng.normal(40.0, 2.0, 6),
        }
    )

    class _FakeExplainer:
        """Tiny SHAP explainer double for a fast artifact smoke test."""

        def shap_values(self, x_test: pd.DataFrame) -> np.ndarray:
            return np.zeros((len(x_test), len(x_test.columns)))

        def __call__(self, x_test: pd.DataFrame) -> object:
            return {"rows": len(x_test), "cols": len(x_test.columns)}

    def fake_tree_explainer(model: object) -> _FakeExplainer:
        return _FakeExplainer()

    def fake_summary_plot(
        shap_values: np.ndarray,
        x_test: pd.DataFrame,
        show: bool = False,
    ) -> None:
        plt.plot([0, 1], [0, 1])

    def fake_bar(
        explanation: object,
        show: bool = False,
    ) -> None:
        plt.plot([0, 1], [1, 0])

    def fake_savefig(path: Path) -> None:
        path.write_bytes(b"fake-png")

    output_dir = Path("scratch") / "shap_artifacts_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts = save_tree_shap_artifacts(
        object(),
        x,
        output_dir,
        explainer_factory=fake_tree_explainer,
        summary_plot_fn=fake_summary_plot,
        bar_plot_fn=fake_bar,
        savefig_fn=fake_savefig,
        close_fn=plt.close,
    )

    assert artifacts["summary"].exists()
    assert artifacts["bar"].exists()
    assert artifacts["summary"].stat().st_size > 0
    assert artifacts["bar"].stat().st_size > 0

def test_get_top_shap_features_returns_sorted_dict() -> None:
    """get_top_shap_features should return top features by importance."""
    # Create tiny dataset
    x = pd.DataFrame({"A": [1, 2, 3], "B": [10, 20, 30], "C": [100, 200, 300]})
    y = [1.1, 2.1, 3.1]

    # Fit tiny model
    model = xgb.XGBRegressor(n_estimators=5, max_depth=2, random_state=42)
    model.fit(x, y)

    # Get top 2
    top = get_top_shap_features(model, x, top_n=2)

    assert isinstance(top, dict)
    assert len(top) == 2
    # The output keys must be strings
    for k in top.keys():
        assert isinstance(k, str)
