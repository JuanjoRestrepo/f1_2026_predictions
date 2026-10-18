"""The served artifact and its provenance sidecar must agree.

The container loads a serialized XGBoost model that is committed to the
repository. That binary cannot explain when it was trained or on which feature
set, so ``scripts/refresh_serving_artifact.py`` writes a sidecar. This test makes
the sidecar load-bearing: a refresh that forgets it, or a hand-edited artifact,
fails here instead of drifting silently in production.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pytest

ARTIFACT = Path("data/outputs/models/xgb_pace_model.joblib")


@pytest.mark.skipif(not ARTIFACT.exists(), reason="serving artifact not present")
def test_metadata_matches_the_serialized_feature_list() -> None:
    """The sidecar must describe exactly the features the binary carries."""
    state = joblib.load(ARTIFACT)
    metadata_path = ARTIFACT.with_suffix(".metadata.json")

    assert metadata_path.exists(), (
        "Missing provenance sidecar. Re-run scripts/refresh_serving_artifact.py."
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert metadata["features"] == state["features"]
    assert metadata["feature_count"] == len(state["features"])
    assert metadata["trained_at_utc"]
    assert metadata["train_years"]
    assert metadata["predict_year"] not in metadata["train_years"]
