"""Model observability script: analyze residuals after a race.

This script compares predicted race pace (standings.csv) against actual 
real-world performance fetched via FastF1. It calculates residuals, 
error metrics (MAE, RMSE), and 'Interval Coverage' to assess model reliability.

Usage:
    uv run python scripts/analyze_residuals.py --year 2024 --round 6 --event "Miami Grand Prix"
"""

import argparse
import logging
from pathlib import Path

import pandas as pd
import numpy as np
import fastf1

from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import configure_root_pipeline_logger, get_logger

logger = get_logger(__name__)

def run_residual_analysis(year: int, round_number: int, event_name: str) -> float | None:
    """Compare predicted vs actual results and report error metrics.
    
    Returns:
        The Mean Absolute Error (MAE) in seconds, or None if analysis failed.
    """
    settings = get_settings()
    safe_event = event_name.replace(" ", "_")
    
    # 1. Load Predictions
    pred_path = Path(settings.reports_dir) / str(year) / safe_event / "results" / "standings.csv"
    if not pred_path.exists():
        logger.error("Predictions not found for %s %d at %s", event_name, year, pred_path)
        return None
        
    df_pred = pd.read_csv(pred_path)
    
    # 2. Fetch Actual Results from FastF1
    logger.info("Fetching actual results for %s %d (Round %d)...", event_name, year, round_number)
    fastf1.Cache.enable_cache(str(settings.fastf1_cache_dir))
    
    try:
        session = fastf1.get_session(year, round_number, 'R')
        session.load(laps=True, telemetry=False, weather=False, messages=False)
    except Exception as e:
        logger.error("Failed to load FastF1 session: %s", e)
        return None
        
    # Calculate actual median lap time per driver
    # Filter for clean laps: no pit stops, valid lap time
    actual_laps = session.laps.copy()
    actual_laps = actual_laps[
        (actual_laps['PitInTime'].isna()) & 
        (actual_laps['PitOutTime'].isna()) & 
        (actual_laps['LapTime'].notna())
    ]
    
    actual_laps['LapTime_s'] = actual_laps['LapTime'].dt.total_seconds()
    
    actual_stats = (
        actual_laps.groupby('Driver')['LapTime_s']
        .median()
        .to_frame('actual_median_s')
        .reset_index()
    )
    
    # 3. Join and Calculate Residuals
    df_merged = df_pred.merge(actual_stats, on='Driver', how='inner')
    
    if df_merged.empty:
        logger.error("Could not match any drivers between predictions and actual results.")
        return None
        
    df_merged['residual_s'] = df_merged['actual_median_s'] - df_merged['median_predicted_s']
    df_merged['abs_error_s'] = df_merged['residual_s'].abs()
    
    # Coverage check: did the actual time fall within the P05-P95 range?
    df_merged['in_range'] = (df_merged['actual_median_s'] >= df_merged['lower_bound_s']) & \
                             (df_merged['actual_median_s'] <= df_merged['upper_bound_s'])
                             
    # 4. Metrics Summary
    mae = df_merged['abs_error_s'].mean()
    rmse = np.sqrt((df_merged['residual_s']**2).mean())
    coverage_pct = df_merged['in_range'].mean() * 100
    
    logger.info("=" * 60)
    logger.info("RESIDUAL ANALYSIS: %s %d", event_name, year)
    logger.info("=" * 60)
    logger.info("Mean Absolute Error (MAE):  %.3fs", mae)
    logger.info("Root Mean Square Error:     %.3fs", rmse)
    logger.info("Interval Coverage (90%% CI): %.1f%%", coverage_pct)
    logger.info("-" * 60)
    
    # Sort by absolute error to see the "Big Misses"
    df_merged = df_merged.sort_values('abs_error_s', ascending=False)
    
    print("\nResidual Table (Top Misses First):")
    print(df_merged[['Driver', 'actual_median_s', 'median_predicted_s', 'residual_s', 'in_range']].to_string(index=False))
    
    # 5. Save Analysis
    output_path = pred_path.parent / "residual_analysis.csv"
    df_merged.to_csv(output_path, index=False)
    logger.info("Residual analysis saved to: %s", output_path)
    
    return float(mae)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze model residuals after a race.")
    parser.add_argument("--year", type=int, required=True, help="Year of the race")
    parser.add_argument("--round", type=int, required=True, help="Round number")
    parser.add_argument("--event", type=str, required=True, help="Event name")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    
    args = parser.parse_args()
    configure_root_pipeline_logger(level=args.log_level)
    
    run_residual_analysis(year=args.year, round_number=args.round, event_name=args.event)
