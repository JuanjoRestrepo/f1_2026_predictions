"""Configuration management for the f1_predictions pipeline.

Rationale for Pydantic Settings (v2):
    - Reads from environment variables AND .env files in a single class.
    - Provides static type safety on all config values — mypy enforces this
      at import time, catching misconfigured paths before the pipeline runs.
    - BaseSettings.model_validate() raises a clear ValidationError on
      startup if required fields are missing, failing fast rather than
      surfacing KeyErrors deep in the pipeline.
    - Alternative considered: plain dataclasses + python-dotenv. Rejected
      because it requires manual type coercion and lacks field-level
      validators and alias support.

Usage::

    from f1_predictions.utils.config import get_settings

    settings = get_settings()
    print(settings.fastf1_cache_dir)

Environment variables (see .env.example for full reference):
    F1_FASTF1_CACHE_DIR : Absolute path for FastF1 telemetry cache.
    F1_DATA_RAW_DIR     : Root directory for raw parquet outputs.
    F1_DATA_PROCESSED_DIR: Root directory for cleaned parquet outputs.
    F1_DATA_OUTPUTS_DIR : Root directory for model prediction outputs.
    F1_MODELS_DIR       : Directory for serialized model artifacts.
    F1_REPORTS_DIR      : Directory for HTML and figure report outputs.
    F1_LOG_LEVEL        : Logging level (DEBUG, INFO, WARNING, ERROR).
    F1_TARGET_SEASON    : Integer season year for the active prediction run.
    F1_RANDOM_SEED      : Global random seed for reproducible model training.
    F1_CV_N_SPLITS      : Number of folds for TimeSeriesSplit cross-validation.
    F1_GMAIL_USER       : Gmail address for outbound race briefing emails.
    F1_GMAIL_APP_PASSWORD: 16-char Google App Password (not the account password).
    F1_RECIPIENT_EMAIL  : Destination email address for race briefings.
    F1_DISCORD_WEBHOOK_URL: Discord webhook URL for race card notifications.
"""

import functools
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration object for the f1_predictions pipeline.

    All fields are sourced from environment variables or the project .env
    file. No default should be a hardcoded secret or an absolute path that
    only exists on one machine — use relative paths anchored to project_root.

    Attributes:
        fastf1_cache_dir: Absolute path where FastF1 caches telemetry.
            FastF1 downloads are large (~500MB per season); this must point
            to a directory outside the repository to avoid accidental commits.
        data_raw_dir: Root for raw parquet outputs from the ingestion stage.
        data_processed_dir: Root for cleaned parquet outputs from cleaning stage.
        data_outputs_dir: Root for prediction parquet outputs.
        models_dir: Root for serialized model artifacts (joblib/pkl).
        reports_dir: Root for HTML sweetviz reports and matplotlib figures.
        log_level: Python logging level string. Validated to accepted values.
        target_season: Active F1 season year for the prediction run.
        random_seed: Global seed passed to numpy, scikit-learn, XGBoost.
        cv_n_splits: Folds for TimeSeriesSplit; recommended >= 5 for F1 data.
    """

    model_config = SettingsConfigDict(
        # Load from .env at the project root. Path is relative to the
        # working directory where the pipeline is invoked (project root).
        env_file=".env",
        env_file_encoding="utf-8",
        # All env vars are prefixed with F1_ to avoid namespace collisions.
        env_prefix="F1_",
        # Ignore unknown fields (e.g. from Trigger.dev or other cloud environments).
        extra="ignore",
        # Re-validate on assignment to catch runtime mutations.
        validate_assignment=True,
    )

    # ── Data paths ────────────────────────────────────────────────────────
    fastf1_cache_dir: Path = Field(
        default=Path("fastf1_cache"),
        description="FastF1 telemetry cache directory. "
        "Set to an absolute path outside the repo.",
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="Google Gemini API Key for the AI Race Summarizer.",
    )

    # ── Notification system (all optional — pipeline runs without them) ──
    gmail_user: str | None = Field(
        default=None,
        description="Gmail address used as sender for race briefing emails.",
    )
    gmail_app_password: str | None = Field(
        default=None,
        description="Google App Password (16 chars). "
        "Generate at myaccount.google.com/apppasswords.",
    )
    recipient_email: str | None = Field(
        default=None,
        description="Destination email address for race briefings.",
    )
    discord_webhook_url: str | None = Field(
        default=None,
        description="Discord Webhook URL for race card embed notifications.",
    )
    data_raw_dir: Path = Field(
        default=Path("data/raw"),
        description="Raw parquet outputs from ingestion stage.",
    )
    data_processed_dir: Path = Field(
        default=Path("data/processed"),
        description="Cleaned parquet outputs from cleaning stage.",
    )
    data_outputs_dir: Path = Field(
        default=Path("data/outputs"),
        description="Model prediction parquet outputs.",
    )
    data_external_dir: Path = Field(
        default=Path("data/external"),
        description="External metadata (e.g. track characteristics).",
    )
    models_dir: Path = Field(
        default=Path("models/artifacts"),
        description="Serialized model artifacts (joblib).",
    )
    reports_dir: Path = Field(
        default=Path("reports"),
        description="HTML reports and figure exports.",
    )

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = Field(
        default="INFO",
        description="Python logging level. "
        "One of: DEBUG, INFO, WARNING, ERROR, CRITICAL.",
    )

    # ── Pipeline parameters ───────────────────────────────────────────────
    target_season: int = Field(
        default=2025,
        ge=2018,  # FastF1 data is reliable from 2018 onward
        le=2030,
        description="Active F1 season year for the prediction run.",
    )
    random_seed: int = Field(
        default=42,
        ge=0,
        description="Global random seed for numpy, scikit-learn, and XGBoost.",
    )
    cv_n_splits: int = Field(
        default=5,
        ge=3,
        le=20,
        description="Number of folds for TimeSeriesSplit cross-validation.",
    )

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log_level is a valid Python logging level name.

        Args:
            v: The raw string value from the environment variable.

        Returns:
            The uppercased log level string.

        Raises:
            ValueError: If the value is not a recognized logging level.
        """
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = v.upper()
        if normalized not in valid_levels:
            msg = f"log_level must be one of {valid_levels}, got '{v}'"
            raise ValueError(msg)
        return normalized

    @field_validator(
        "fastf1_cache_dir",
        "data_raw_dir",
        "data_processed_dir",
        "data_outputs_dir",
        "data_external_dir",
        "models_dir",
        "reports_dir",
        mode="after",
    )
    @classmethod
    def resolve_and_mkdir(cls, v: Path) -> Path:
        """Resolve the path to absolute and create it if it does not exist.

        Creating directories on validation ensures the pipeline never fails
        mid-run due to a missing output directory. Idempotent: safe to call
        on every startup.

        Args:
            v: The Path value after initial Pydantic parsing.

        Returns:
            The resolved absolute Path, guaranteed to exist on disk.
        """
        resolved = v.resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance for the pipeline.

    Uses lru_cache to ensure .env is parsed only once per process,
    regardless of how many modules call get_settings(). This is the
    canonical entry point — do not instantiate Settings() directly.

    Returns:
        The validated, cached Settings instance.

    Example::

        from f1_predictions.utils.config import get_settings

        settings = get_settings()
        cache_dir = settings.fastf1_cache_dir
    """
    return Settings()
