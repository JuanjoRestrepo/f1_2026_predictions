"""Centralized logging configuration for the f1_predictions pipeline.

Rationale for this module:
    - All pipeline stages import get_logger() from here. This guarantees
      a single, consistent logging configuration across ingestion, cleaning,
      feature engineering, modeling, and evaluation — regardless of entry
      point (Jupyter notebook, CLI script, or test runner).
    - Using the logging module (not print) provides: level filtering,
      structured formatting with timestamps, file rotation, and easy
      integration with external log aggregators (e.g., CloudWatch, Datadog).
    - The root logger is intentionally NOT configured here. Only a named
      logger hierarchy under 'f1_predictions' is touched, which prevents
      this module from silencing third-party library logs (FastF1, XGBoost).

Design decisions:
    - Two handlers by default: StreamHandler (stdout) and RotatingFileHandler.
    - File rotation: 5MB per file, 3 backups — prevents unbounded log growth
      during multi-race season runs.
    - JSON-structured logs are NOT implemented here. If log aggregation is
      required in a future production deployment, replace the Formatter with
      python-json-logger. Document that change in this module's docstring.
    - Idempotent: calling get_logger() multiple times for the same name is
      safe — handlers are only added once per logger instance.

Usage::

    from f1_predictions.utils.logging_setup import get_logger

    logger = get_logger(__name__)
    logger.info("Session loaded: %s", session_key)
    logger.warning("Null laps detected: %d rows dropped", n_dropped)
    logger.error("FastF1 API call failed", exc_info=True)
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

# The root namespace for all pipeline loggers.
# Using a hierarchy (f1_predictions.ingestion, f1_predictions.cleaning, etc.)
# allows callers to filter by stage via logging.getLogger("f1_predictions").
_ROOT_LOGGER_NAME: str = "f1_predictions"

# Log format: timestamp | level | module name | message
# The module name (%(name)s) is set by passing __name__ to get_logger(),
# which produces hierarchical names like f1_predictions.ingestion.loader.
_LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# Default log directory — resolved relative to the project root.
# Override via the F1_LOG_LEVEL env var (see utils/config.py).
_DEFAULT_LOG_DIR: Path = Path("logs")
_DEFAULT_LOG_FILENAME: str = "f1_pipeline.log"

# Rotation: 5MB per file, keep 3 backups (15MB total ceiling)
_MAX_BYTES: int = 5 * 1024 * 1024
_BACKUP_COUNT: int = 3


# ── Internal helpers ─────────────────────────────────────────────────────────


def _build_formatter() -> logging.Formatter:
    """Build the shared log formatter.

    Returns:
        A Formatter instance with timestamp, level, name, and message fields.
    """
    return logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)


def _add_stream_handler(logger: logging.Logger, level: int) -> None:
    """Attach a stdout StreamHandler if one is not already present.

    Idempotent: checks existing handlers before adding to avoid duplicate
    log lines when get_logger() is called multiple times (common in notebooks
    where cells are re-executed without a kernel restart).

    Args:
        logger: The logger instance to configure.
        level: The logging level integer (e.g., logging.INFO).
    """
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            return  # Already attached — skip

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(_build_formatter())
    logger.addHandler(stream_handler)


def _add_file_handler(
    logger: logging.Logger,
    level: int,
    log_dir: Path,
    filename: str,
) -> None:
    """Attach a RotatingFileHandler if one is not already present.

    Creates the log directory if it does not exist. Idempotent.

    Args:
        logger: The logger instance to configure.
        level: The logging level integer.
        log_dir: Directory where the log file will be written.
        filename: Name of the log file within log_dir.
    """
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            return  # Already attached — skip

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / filename

    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(_build_formatter())
    logger.addHandler(file_handler)


# ── Public API ───────────────────────────────────────────────────────────────


def configure_root_pipeline_logger(
    level: str = "INFO",
    log_dir: Path = _DEFAULT_LOG_DIR,
    filename: str = _DEFAULT_LOG_FILENAME,
    enable_file_logging: bool = True,
) -> None:
    """Configure the root 'f1_predictions' logger once per process.

    Call this exactly once at the pipeline entry point (main script or
    the first cell of a Jupyter notebook). All child loggers created via
    get_logger(__name__) will inherit this configuration automatically.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            Defaults to "INFO". Override with the F1_LOG_LEVEL env var.
        log_dir: Directory for the rotating log file. Created if absent.
        filename: Log filename within log_dir.
        enable_file_logging: Set to False in notebook environments to avoid
            creating log files during interactive exploration.

    Example::

        # At the top of the pipeline entry point or notebook cell 1:
        from f1_predictions.utils.logging_setup import configure_root_pipeline_logger

        configure_root_pipeline_logger(level="DEBUG", enable_file_logging=False)
    """
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        msg = (
            f"Invalid log level: '{level}'. Must be DEBUG/INFO/WARNING/ERROR/CRITICAL."
        )
        raise TypeError(msg)

    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    root_logger.setLevel(numeric_level)

    # Prevent log records from propagating to the Python root logger,
    # which would cause duplicate output if the root logger has handlers.
    root_logger.propagate = False

    _add_stream_handler(root_logger, numeric_level)

    if enable_file_logging:
        _add_file_handler(root_logger, numeric_level, log_dir, filename)


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger under the 'f1_predictions' hierarchy.

    This is the only function pipeline modules should call. Passing __name__
    produces hierarchical logger names (e.g., f1_predictions.ingestion.loader)
    which allows granular filtering without changing the logging configuration.

    Args:
        name: The module's __name__ string. Always pass __name__ — never
            construct the name manually to avoid hierarchy mismatches.

    Returns:
        A Logger instance that inherits level and handlers from the root
        'f1_predictions' logger configured by configure_root_pipeline_logger().

    Example::

        # In any pipeline module:
        from f1_predictions.utils.logging_setup import get_logger

        logger = get_logger(__name__)

        def load_session(year: int, round_number: int) -> None:
            logger.info("Loading session: year=%d round=%d", year, round_number)
            try:
                ...
            except Exception:
                logger.exception("Session load failed")
                raise
    """
    # Ensure the child logger name is always under the f1_predictions namespace.
    # If the caller passes a top-level name (e.g., "__main__"), prefix it.
    if not name.startswith(_ROOT_LOGGER_NAME):
        qualified_name = f"{_ROOT_LOGGER_NAME}.{name}"
    else:
        qualified_name = name

    return logging.getLogger(qualified_name)
