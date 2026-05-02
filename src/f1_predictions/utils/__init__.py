"""Utility modules for the f1_predictions pipeline.

Public API:
    get_logger              : Return a named child logger under 'f1_predictions'.
    configure_root_pipeline_logger: Initialize logging once at the entry point.
    get_settings            : Return the cached, validated Settings singleton.
    quick_profile           : Print a compact DataFrame profile to stdout.
"""

from f1_predictions.utils.config import Settings, get_settings
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)
from f1_predictions.utils.profiling import quick_profile

__all__ = [
    "Settings",
    "configure_root_pipeline_logger",
    "get_logger",
    "get_settings",
    "quick_profile",
]
