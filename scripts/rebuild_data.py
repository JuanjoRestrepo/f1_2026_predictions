"""Script to rebuild all Silver and Gold Parquet files from Raw data."""
import sys
from pathlib import Path
import re

from f1_predictions.ingestion.fastf1_client import SessionKey
from f1_predictions.cleaning.pipeline import run_cleaning_pipeline
from f1_predictions.features.pipeline import run_feature_pipeline
from f1_predictions.utils.logging_setup import configure_root_pipeline_logger, get_logger

configure_root_pipeline_logger("INFO")
logger = get_logger(__name__)

def rebuild_all():
    raw_dir = Path("data/raw/laps")
    if not raw_dir.exists():
        logger.error("Raw laps dir not found.")
        sys.exit(1)
        
    files = list(raw_dir.rglob("race_laps.parquet"))
    logger.info("Found %d raw lap files to rebuild.", len(files))
    
    # We need to preserve EventName, but we can dummy it if we bypass FastF1.
    # Actually, run_cleaning_pipeline doesn't use key.event_name, it just uses year/round for paths.
    # Let's extract year and round from the path.
    # Path format: season=2023/round=01/race_laps.parquet
    
    for idx, f in enumerate(files, 1):
        try:
            season_match = re.search(r"season=(\d{4})", str(f))
            round_match = re.search(r"round=(\d{2})", str(f))
            if not season_match or not round_match:
                logger.warning("Could not parse season/round from %s", f)
                continue
                
            year = int(season_match.group(1))
            round_num = int(round_match.group(1))
            
            # Event name is not strictly needed for path resolution, just pass a dummy string
            key = SessionKey(year=year, round_number=round_num, identifier="R", event_name="Unknown")
            
            logger.info("[%d/%d] Rebuilding %s Round %s...", idx, len(files), year, round_num)
            
            run_cleaning_pipeline(key, session_type="race", overwrite=True)
            run_feature_pipeline(key, overwrite=True)
            
        except Exception as e:
            logger.error("Failed to rebuild %s: %s", f, e)

if __name__ == "__main__":
    rebuild_all()
