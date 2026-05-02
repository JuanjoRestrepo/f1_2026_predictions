"""Parquet serialisation for the f1_predictions ingestion stage.

Rationale for Parquet as the canonical storage format:
    Parquet is the standard for analytical pipelines because it provides:
        - Columnar storage with predicate pushdown (fast season/round filters).
        - Built-in snappy compression (~4x smaller than CSV).
        - Preserved dtypes across reads — no silent re-inference of timedelta
          columns as strings (a common CSV pitfall with F1 timing data).
        - Native partition support, enabling race-by-race append semantics.
    CSV is explicitly rejected for Silver/Gold layer data as per the project's
    storage format policy (see pyproject.toml rationale and SKILL.md).

Idempotency contract:
    Writing the same session twice must produce the same file and not corrupt
    existing data. The ``overwrite`` parameter (default ``False``) controls
    whether an existing file is replaced. When ``overwrite=False`` and the
    file exists, the write is skipped and the existing path is returned.
    This ensures re-running the full-season ingestion loop does not re-download
    and re-write sessions that already exist on disk.

Partitioning strategy:
    Files are written to:
        ``{base_dir}/{data_type}/season={year}/round={round:02d}/``
    This Hive-style partitioning enables pandas ``read_parquet()`` with
    ``filters=[("season", "==", 2025)]`` for efficient season-scoped loads
    and is compatible with Spark/DuckDB for future scale-out.

    Example paths:
        data/raw/laps/season=2025/round=01/qualifying_laps.parquet
        data/raw/results/season=2025/round=01/race_results.parquet
        data/raw/weather/season=2025/round=01/race_weather.parquet
"""

from enum import Enum
from pathlib import Path

import pandas as pd

from f1_predictions.ingestion.fastf1_client import SessionKey
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Parquet engine: pyarrow is chosen over fastparquet for two reasons:
#   1. pyarrow preserves pandas Timedelta columns natively.
#   2. pyarrow is the de-facto standard, widely supported in the ecosystem.
_PARQUET_ENGINE: str = "pyarrow"

# Snappy compression: best balance of speed and ratio for F1 telemetry data.
# zstd would give better compression but adds a C dependency; not worth it here.
_PARQUET_COMPRESSION: str = "snappy"


# ── Data type enum ────────────────────────────────────────────────────────────

class DataType(str, Enum):
    """Enumeration of the data types written by the ingestion stage.

    Using an Enum instead of raw strings prevents silent typos in directory
    names and makes all valid data types discoverable via IDE autocomplete.

    Attributes:
        LAPS: Lap-level timing and tyre data.
        RESULTS: Session results (qualifying times or race classification).
        WEATHER: Session-level weather summary.
    """

    LAPS = "laps"
    RESULTS = "results"
    WEATHER = "weather"


# ── Path resolution ───────────────────────────────────────────────────────────

def resolve_parquet_path(
    key: SessionKey,
    data_type: DataType,
    base_dir: Path | None = None,
) -> Path:
    """Compute the canonical Parquet output path for a session and data type.

    The path follows Hive-style partitioning:
        ``{base_dir}/{data_type}/season={year}/round={round:02d}/{session}_{type}.parquet``

    Args:
        key: The ``SessionKey`` identifying the session.
        data_type: The ``DataType`` variant (laps, results, or weather).
        base_dir: Override for the base data directory. Defaults to
            ``Settings.data_raw_dir`` if ``None``.

    Returns:
        The resolved absolute ``Path`` for the Parquet file.
        The parent directory is created if it does not exist.

    Example::

        from f1_predictions.ingestion.fastf1_client import SessionKey
        from f1_predictions.ingestion.parquet_writer import resolve_parquet_path, DataType

        key = SessionKey(year=2025, round_number=1, identifier="Q", event_name="Bahrain GP")
        path = resolve_parquet_path(key, DataType.LAPS)
        # → data/raw/laps/season=2025/round=01/qualifying_laps.parquet
    """
    if base_dir is None:
        base_dir = get_settings().data_raw_dir

    # Hive-style partition directories
    partition_dir = (
        base_dir
        / data_type.value
        / f"season={key.year}"
        / f"round={key.round_number:02d}"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)

    # File name: <session_type_lower>_<data_type>.parquet
    # e.g., qualifying_laps.parquet, race_results.parquet
    session_label = key.identifier.lower().replace("q", "qualifying").replace("r", "race")
    filename = f"{session_label}_{data_type.value}.parquet"

    return partition_dir / filename


# ── Writer ────────────────────────────────────────────────────────────────────

def write_parquet(
    df: pd.DataFrame,
    key: SessionKey,
    data_type: DataType,
    base_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Write a DataFrame to a partitioned Parquet file.

    Idempotency guarantee: if the target file already exists and
    ``overwrite=False``, the write is skipped and the existing path is
    returned. This makes it safe to re-run the full ingestion loop without
    re-downloading already-cached sessions.

    Args:
        df: The DataFrame to serialise. Must not be empty.
        key: The ``SessionKey`` for path partitioning and logging context.
        data_type: The ``DataType`` variant determining the subdirectory.
        base_dir: Override for the base directory. Uses
            ``Settings.data_raw_dir`` when ``None``.
        overwrite: If ``True``, overwrite any existing file. If ``False``
            (default), skip the write and return the existing path.

    Returns:
        The absolute ``Path`` of the written (or existing) Parquet file.

    Raises:
        ValueError: If ``df`` is empty — writing empty Parquet files would
            silently corrupt downstream pipeline runs.
        OSError: If the target directory cannot be created or the file
            cannot be written (e.g., permission error).

    Example::

        from f1_predictions.ingestion.parquet_writer import write_parquet, DataType

        path = write_parquet(race_data.laps, key, DataType.LAPS)
        logger.info("Laps written to %s", path)
    """
    if df.empty:
        msg = (
            f"Refusing to write empty DataFrame for {key} / {data_type.value}. "
            "Check the session load and extraction steps."
        )
        raise ValueError(msg)

    target_path = resolve_parquet_path(key, data_type, base_dir)

    if target_path.exists() and not overwrite:
        logger.info(
            "Parquet file already exists, skipping write (overwrite=False): %s",
            target_path,
        )
        return target_path

    try:
        df.to_parquet(
            target_path,
            engine=_PARQUET_ENGINE,
            compression=_PARQUET_COMPRESSION,
            index=False,  # Pandas RangeIndex carries no information — drop it.
        )
    except OSError as exc:
        logger.error(
            "Failed to write Parquet file %s: %s",
            target_path, exc,
        )
        raise

    file_size_kb = target_path.stat().st_size / 1024
    logger.info(
        "Parquet written: %s | rows=%d  cols=%d  size=%.1fKB",
        target_path, len(df), len(df.columns), file_size_kb,
    )
    return target_path


def read_parquet(
    key: SessionKey,
    data_type: DataType,
    base_dir: Path | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Read a partitioned Parquet file back into a DataFrame.

    Provided here so all Parquet I/O for the ingestion layer goes through
    a single module. Downstream stages (cleaning, features) should call
    this function rather than constructing paths manually.

    Args:
        key: The ``SessionKey`` identifying the session to read.
        data_type: The ``DataType`` variant to read.
        base_dir: Override for the base directory.
        columns: Optional list of column names to load. When provided,
            only those columns are read (predicate pushdown via pyarrow).
            Pass ``None`` to load all columns.

    Returns:
        A DataFrame containing the requested data.

    Raises:
        FileNotFoundError: If the Parquet file does not exist.
            This is a hard error — callers must run ingestion before cleaning.

    Example::

        from f1_predictions.ingestion.parquet_writer import read_parquet, DataType

        laps = read_parquet(key, DataType.LAPS, columns=["Driver", "LapTime", "Compound"])
    """
    target_path = resolve_parquet_path(key, data_type, base_dir)

    if not target_path.exists():
        msg = (
            f"Parquet file not found: {target_path}. "
            "Run the ingestion stage for this session before attempting to read."
        )
        raise FileNotFoundError(msg)

    df = pd.read_parquet(target_path, engine=_PARQUET_ENGINE, columns=columns)
    logger.debug(
        "Parquet read: %s | rows=%d  cols=%d",
        target_path, len(df), len(df.columns),
    )
    return df
