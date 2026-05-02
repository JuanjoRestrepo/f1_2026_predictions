"""f1_predictions — F1 2026 race prediction pipeline.

Package structure:
    ingestion   : FastF1 API client and session loaders.
    cleaning    : Lap time normalization, outlier filtering, imputation.
    features    : Feature engineering and encoding for the ML pipeline.
    modeling    : XGBoost regressor wrapper and Linear Regression baseline.
    evaluation  : MAE computation, driver ranking matrix, SHAP analysis.
    utils       : Logging setup, config loader, schema validators, profiling.

Usage:
    This package is intended to be imported from production modules and
    Jupyter notebooks alike. All public entry points are re-exported here
    to provide a stable import surface::

        from f1_predictions.utils.logging_setup import get_logger
        from f1_predictions.utils.config import Settings

Notes:
    - Never import side-effectful code at the top level of this module.
      Config loading and logger initialization must be deferred to call sites.
    - All sub-packages expose their own __init__.py with explicit __all__.
"""

__version__ = "0.1.0"
__author__ = "Juan Jose Restrepo Rosero"
