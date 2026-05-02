"""Full-season data ingestion script: Bronze → Silver → Gold pipeline.

Usage:
    uv run python scripts/ingest_season.py --year 2024 --max-rounds 24
    uv run python scripts/ingest_season.py --year 2023 --max-rounds 22

This script orchestrates the three pipeline stages for every race in a season:
    1. Bronze: FastF1 API  → raw Parquet  (data/raw/)
    2. Silver: cleaning    → clean Parquet (data/processed/)
    3. Gold:   features    → feature matrix (data/outputs/)

Idempotency: Each stage checks for existing Parquets and skips re-processing
unless --overwrite is passed. Safe to re-run after a partial failure.
"""

import argparse
import logging
import sys
import time

from f1_predictions.cleaning.pipeline import run_cleaning_pipeline
from f1_predictions.features.pipeline import run_feature_pipeline
from f1_predictions.ingestion.fastf1_client import load_session
from f1_predictions.ingestion.parquet_writer import DataType, write_parquet
from f1_predictions.ingestion.session_loader import load_race
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# F1 points system (2010 onwards)
POINTS_MAP: dict[int, float] = {
    1: 25,
    2: 18,
    3: 15,
    4: 12,
    5: 10,
    6: 8,
    7: 6,
    8: 4,
    9: 2,
    10: 1,
}


def ingest_round(
    year: int,
    round_number: int,
    overwrite: bool = False,
) -> bool:
    """Download, clean, and featurise a single race round.

    Args:
        year: Championship season year.
        round_number: Round number within the season (1-indexed).
        overwrite: If True, re-process even if files already exist.

    Returns:
        True if the round was processed successfully, False if skipped or failed.
    """
    logger.info("=" * 60)
    logger.info("Processing %d Round %02d", year, round_number)
    logger.info("=" * 60)

    # ── Stage 1: FastF1 ingestion (Bronze) ────────────────────────────────
    try:
        session, key = load_session(year, round_number, "R")
    except Exception:
        logger.exception(
            "Failed to load session %d R%02d. Skipping round.", year, round_number
        )
        return False

    race_data = load_race(session, key)

    # Write Bronze Parquets
    write_parquet(race_data.laps, key, DataType.LAPS, overwrite=overwrite)
    write_parquet(race_data.results, key, DataType.RESULTS, overwrite=overwrite)
    if not race_data.weather.empty:
        write_parquet(race_data.weather, key, DataType.WEATHER, overwrite=overwrite)

    logger.info(
        "Bronze written: %d laps, %d drivers",
        len(race_data.laps),
        len(race_data.results),
    )

    # ── Stage 2: Cleaning (Silver) ─────────────────────────────────────────
    try:
        cleaning_report = run_cleaning_pipeline(
            key, session_type="race", overwrite=overwrite
        )
        logger.info(
            "Silver written: %d rows retained (%.1f%%)",
            cleaning_report.clean_row_count,
            cleaning_report.retention_pct,
        )
    except Exception:
        logger.exception("Cleaning failed for %s. Skipping feature stage.", key)
        return False

    # ── Stage 3: Feature Engineering (Gold) ───────────────────────────────
    try:
        _, feat_report = run_feature_pipeline(key, overwrite=overwrite)
        logger.info(
            "Gold written: %d rows x %d features -> %s",
            feat_report.output_row_count,
            feat_report.output_col_count,
            feat_report.output_path,
        )
    except Exception:
        logger.exception("Feature pipeline failed for %s.", key)
        return False

    return True


def ingest_season(
    year: int,
    max_rounds: int,
    overwrite: bool,
    delay_seconds: float,
) -> None:
    """Iterate over all rounds in a season and ingest each one.

    Args:
        year: Championship season year.
        max_rounds: Maximum rounds to attempt (use season length).
        overwrite: Whether to re-process existing files.
        delay_seconds: Seconds to wait between rounds (respects FastF1 CDN rate limits).
    """
    successes: list[int] = []
    failures: list[int] = []

    for round_number in range(1, max_rounds + 1):
        ok = ingest_round(year, round_number, overwrite=overwrite)
        if ok:
            successes.append(round_number)
        else:
            failures.append(round_number)

        if round_number < max_rounds:
            logger.info("Waiting %.1fs before next round...", delay_seconds)
            time.sleep(delay_seconds)

    logger.info("=" * 60)
    logger.info(
        "Season %d ingestion complete: %d OK, %d failed",
        year,
        len(successes),
        len(failures),
    )
    if failures:
        logger.warning("Failed rounds: %s", failures)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the ingestion script."""
    parser = argparse.ArgumentParser(
        description="Ingest a full F1 season: Bronze -> Silver -> Gold.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--year", type=int, required=True, help="Championship season year (e.g. 2024)."
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=24,
        help="Maximum rounds to process (use season round count).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-process rounds even if Parquets exist.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between rounds (CDN rate limiting).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Configure root logger level from CLI
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    logger.info(
        "Starting ingestion: year=%d  max_rounds=%d  overwrite=%s",
        args.year,
        args.max_rounds,
        args.overwrite,
    )

    ingest_season(
        year=args.year,
        max_rounds=args.max_rounds,
        overwrite=args.overwrite,
        delay_seconds=args.delay,
    )

    sys.exit(0)
