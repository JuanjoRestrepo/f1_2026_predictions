"""Script to rebuild all Silver and Gold Parquet files from Raw data."""

import re
import sys
from pathlib import Path

import pandas as pd

from f1_predictions.cleaning.pipeline import run_cleaning_pipeline
from f1_predictions.features.pipeline import run_feature_pipeline
from f1_predictions.ingestion.fastf1_client import SessionKey
from f1_predictions.ingestion.parquet_writer import DataType, write_parquet
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

configure_root_pipeline_logger("INFO")
logger = get_logger(__name__)


def _key_from_path(path: Path) -> SessionKey | None:
    """Build a session key from ``season=YYYY/round=NN`` in the path."""
    season_match = re.search(r"season=(\d{4})", str(path))
    round_match = re.search(r"round=(\d{2})", str(path))
    if not season_match or not round_match:
        return None
    year = int(season_match.group(1))
    round_num = int(round_match.group(1))
    # The circuit profile and EventName OHE column depend on the real event
    # name, so read it from the raw parquet instead of passing a dummy.
    event_name = "Unknown"
    try:
        event_name = str(
            pd.read_parquet(path, columns=["EventName"])["EventName"].iloc[0]
        )
    except Exception:  # noqa: BLE001 - a missing column must not abort the rebuild
        logger.warning(
            "EventName unavailable in %s; circuit profile will be default", path
        )
    return SessionKey(
        year=year, round_number=round_num, identifier="R", event_name=event_name
    )


def migrate_results(raw_dir: Path) -> None:
    """Copy raw race results into the processed layer.

    The feature pipeline computes historical points and EWMA form from
    previous rounds' results. Without this migration every round silently
    falls back to the neutral defaults (0 points, P11 form), which makes
    those features constant and unusable.
    """
    settings = get_settings()
    written = 0
    for path in sorted(raw_dir.rglob("race_results.parquet")):
        key = _key_from_path(path)
        if key is None:
            continue
        results = pd.read_parquet(path)
        write_parquet(
            df=results,
            key=key,
            data_type=DataType.RESULTS,
            base_dir=settings.data_processed_dir,
            overwrite=True,
        )
        written += 1
    logger.info("Migrated %d race result files to the processed layer.", written)


def rebuild_all() -> None:
    settings = get_settings()
    raw_dir = Path(settings.data_raw_dir) / "laps"
    if not raw_dir.exists():
        logger.error("Raw laps dir not found.")
        sys.exit(1)

    migrate_results(Path(settings.data_raw_dir) / "results")

    files = list(raw_dir.rglob("race_laps.parquet"))
    logger.info("Found %d raw lap files to rebuild.", len(files))

    for idx, f in enumerate(files, 1):
        try:
            key = _key_from_path(f)
            if key is None:
                logger.warning("Could not parse season/round from %s", f)
                continue

            logger.info(
                "[%d/%d] Rebuilding %s Round %s (%s)...",
                idx,
                len(files),
                key.year,
                key.round_number,
                key.event_name,
            )

            run_cleaning_pipeline(key, session_type="race", overwrite=True)
            run_feature_pipeline(key, overwrite=True)

        except Exception:
            logger.exception("Failed to rebuild %s", f)


if __name__ == "__main__":
    rebuild_all()
