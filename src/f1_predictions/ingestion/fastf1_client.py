"""FastF1 API client with cache configuration and retry logic.

Responsibilities of this module:
    1. Configure the FastF1 disk cache exactly once per process.
    2. Wrap ``fastf1.get_session()`` + ``session.load()`` with retry logic
       via tenacity so transient network failures do not abort long pipeline
       runs over a full season.
    3. Return a typed ``fastf1.core.Session`` object — all downstream
       data extraction happens in ``session_loader.py``, not here.

Why tenacity over a manual retry loop:
    tenacity provides exponential backoff, jitter, configurable stop
    conditions, and before/after hooks for logging — all with a clean
    decorator API. A hand-rolled loop would replicate this poorly.
    The specific strategy chosen (exponential backoff, 3 retries, 2-30s
    wait) reflects FastF1's CDN rate-limiting behaviour: bursts of
    requests are throttled; short waits resolve most transient failures.

Cache configuration note:
    FastF1 caches sessions to disk (default: ~/.cache/fastf1). The cache
    directory is set from Settings.fastf1_cache_dir so it can be pointed
    at a fast SSD or shared network path in production. The cache is
    idempotent: re-running the pipeline for the same session reads from
    disk instead of making API calls, which is critical for reproducibility.

Thread safety:
    FastF1's session loading is not thread-safe. Do not call load_session()
    concurrently. If parallel loading is needed in future, use a process
    pool (not thread pool) and ensure each worker has an isolated cache dir.
"""

import functools
from dataclasses import dataclass, field
from typing import Literal

import fastf1
import fastf1.core
from tenacity import (
    RetryCallState,
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Type aliases ─────────────────────────────────────────────────────────────

# FastF1 session identifier literals — all valid values accepted by
# fastf1.get_session(). Using a Literal type prevents silent typos.
SessionIdentifier = Literal[
    "FP1",
    "FP2",
    "FP3",
    "Q",
    "SQ",  # Qualifying and Sprint Qualifying
    "S",  # Sprint
    "R",  # Race
]

# ── Retry configuration constants ─────────────────────────────────────────────

# Maximum number of attempts before raising RetryError.
# 3 attempts = 1 original + 2 retries. Calibrated to FastF1 CDN behaviour.
_MAX_ATTEMPTS: int = 3

# Exponential backoff: wait 2s, then 4s, then 8s … capped at 30s.
# Jitter is implicit in tenacity's wait_exponential when multiplier > 1.
_WAIT_MIN_SECONDS: int = 2
_WAIT_MAX_SECONDS: int = 30
_WAIT_MULTIPLIER: int = 2

# ── Cache initialisation ──────────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def _configure_fastf1_cache() -> None:
    """Configure the FastF1 disk cache exactly once per process.

    Uses lru_cache(maxsize=1) to guarantee idempotency — calling this
    function multiple times (e.g., from multiple notebooks loaded in the
    same kernel) has no effect after the first call.

    The cache path is read from Settings.fastf1_cache_dir, which is resolved
    to an absolute path and created if absent by Pydantic's validator.
    """
    settings = get_settings()
    cache_dir = settings.fastf1_cache_dir
    fastf1.Cache.enable_cache(str(cache_dir))
    logger.info("FastF1 cache configured at: %s", cache_dir)


# ── Session dataclass ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SessionKey:
    """Immutable identifier for a single F1 session.

    Used as a structured key for logging, file naming, and caching.
    Frozen to prevent accidental mutation during pipeline execution.

    Attributes:
        year: Championship season year (e.g. 2025).
        round_number: Round number within the season calendar (1-indexed).
        identifier: FastF1 session type code (e.g. ``"Q"``, ``"R"``).
        event_name: Human-readable event name populated after loading
            (e.g. ``"Bahrain Grand Prix"``). Empty string before load.
    """

    year: int
    round_number: int
    identifier: SessionIdentifier
    event_name: str = field(default="")

    def __str__(self) -> str:
        """Return a compact string representation for logging and filenames.

        Returns:
            A string in the format ``"2025_R01_Q"`` or
            ``"2025_R01_R - Bahrain Grand Prix"`` when event_name is set.
        """
        base = f"{self.year}_R{self.round_number:02d}_{self.identifier}"
        if self.event_name:
            return f"{base} - {self.event_name}"
        return base


# ── Retry-decorated loader ────────────────────────────────────────────────────


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """Log each retry attempt with context before sleeping.

    This callback is passed to tenacity's ``before_sleep`` hook.
    It surfaces retry attempts in the pipeline log so operators can
    distinguish transient network issues from persistent API failures.

    Args:
        retry_state: The tenacity RetryCallState object carrying attempt
            number, outcome, and next sleep duration.
    """
    attempt = retry_state.attempt_number
    sleep = getattr(retry_state.next_action, "sleep", "?")
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "FastF1 load attempt %d failed (%s). Retrying in %.1fs.",
        attempt,
        type(exc).__name__ if exc else "unknown error",
        sleep,
    )


@retry(
    # Retry on any Exception subclass — FastF1 raises both network errors
    # (requests.exceptions.ConnectionError) and internal errors on corrupt
    # cache entries. Catching Exception broadly is intentional here; the
    # stop condition and logging prevent runaway retries.
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=wait_exponential(
        multiplier=_WAIT_MULTIPLIER,
        min=_WAIT_MIN_SECONDS,
        max=_WAIT_MAX_SECONDS,
    ),
    before_sleep=before_sleep_log(logger, 30),  # 30 = logging.WARNING
    reraise=True,  # Re-raise the original exception after all retries fail
)
def _load_session_with_retry(
    year: int,
    round_number: int,
    identifier: SessionIdentifier,
) -> fastf1.core.Session:
    """Load a FastF1 session with exponential backoff retry.

    This is the inner retry-wrapped call. Not intended for direct use —
    call ``load_session()`` which adds logging and cache setup.

    Args:
        year: Championship season year.
        round_number: Round number within the season calendar.
        identifier: FastF1 session type code (``"Q"``, ``"R"``, etc.).

    Returns:
        A loaded ``fastf1.core.Session`` object.

    Raises:
        RetryError: If all retry attempts are exhausted.
        Any exception from fastf1 or the underlying network layer.
    """
    session = fastf1.get_session(year, round_number, identifier)
    # Load all standard data: laps, results, weather, track status.
    # Telemetry is excluded here (laps=True, telemetry=False by default)
    # because per-driver telemetry is loaded on demand and is expensive.
    session.load(
        laps=True,
        telemetry=False,  # Load via load_telemetry() in features stage
        weather=True,
        messages=False,  # Race control messages not needed for prediction
    )
    return session


# ── Public API ────────────────────────────────────────────────────────────────


def load_session(
    year: int,
    round_number: int,
    identifier: SessionIdentifier,
) -> tuple[fastf1.core.Session, SessionKey]:
    """Load a FastF1 session, returning the session object and its key.

    This is the single entry point for all session loading in the pipeline.
    It configures the cache (idempotent), loads the session with retry
    logic, and returns a structured ``SessionKey`` for downstream use.

    Args:
        year: Championship season year. Must be >= 2018 (FastF1 data origin).
        round_number: Round number within the season calendar (1-indexed).
        identifier: FastF1 session type code. Use ``"Q"`` for qualifying
            and ``"R"`` for race. See ``SessionIdentifier`` for all values.

    Returns:
        A tuple of:
            - ``fastf1.core.Session``: The loaded session object with laps,
              results, and weather data populated.
            - ``SessionKey``: Immutable key for this session, including the
              event name resolved from the FastF1 event schedule.

    Raises:
        ValueError: If ``year < 2018`` or ``round_number < 1``.
        RetryError: If all retry attempts are exhausted after network failures.
        fastf1.core.DataNotLoadedError: If the session has no data (e.g.,
            the session was cancelled or has not yet taken place).

    Example::

        from f1_predictions.ingestion.fastf1_client import load_session

        session, key = load_session(2025, 1, "Q")
        print(key)            # "2025_R01_Q - Bahrain Grand Prix"
        print(session.laps.shape)
    """
    if year < 2018:
        msg = f"FastF1 data is not reliably available before 2018. Got year={year}."
        raise ValueError(msg)
    if round_number < 1:
        msg = f"round_number must be >= 1. Got {round_number}."
        raise ValueError(msg)

    _configure_fastf1_cache()

    logger.info(
        "Loading session: year=%d  round=%d  type=%s",
        year,
        round_number,
        identifier,
    )

    try:
        session = _load_session_with_retry(year, round_number, identifier)
    except RetryError:
        logger.exception(
            "All %d retry attempts exhausted for session %d/%d/%s. "
            "Check network connectivity and FastF1 service status.",
            _MAX_ATTEMPTS,
            year,
            round_number,
            identifier,
        )
        raise

    event_name: str = ""
    try:
        event_name = str(session.event["EventName"])
    except (KeyError, AttributeError):
        logger.warning(
            "Could not resolve event name for session %d/%d/%s.",
            year,
            round_number,
            identifier,
        )

    key = SessionKey(
        year=year,
        round_number=round_number,
        identifier=identifier,
        event_name=event_name,
    )

    logger.info("Session loaded successfully: %s | laps=%d", key, len(session.laps))
    return session, key
