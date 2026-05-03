"""
F1 Prediction Pipeline - Master Orchestrator
-------------------------------------------
This script serves as the main entry point for the entire predictive pipeline.
It orchestrates the virtual race simulation and the subsequent visualization
generation into a single, unified command.

Usage:
    uv run main.py --round 4 --event "Miami Grand Prix"
"""

import argparse
import subprocess
import sys
from f1_predictions.utils.logging_setup import configure_root_pipeline_logger, get_logger

logger = get_logger(__name__)

def run_full_pipeline(year: int, round_num: int, event: str):
    """
    Executes the simulation and visualization scripts sequentially.
    """
    logger.info("=" * 60)
    logger.info(f"ORCHESTRATING PIPELINE: {event} ({year})")
    logger.info("=" * 60)

    try:
        # Step 1: Virtual Race Simulation
        logger.info("STEP 1/2: Running Virtual Race Simulation...")
        sim_cmd = [
            "uv", "run", "scripts/simulate_race.py",
            "--year", str(year),
            "--round", str(round_num),
            "--event", event
        ]
        subprocess.run(sim_cmd, check=True)

        # Step 2: Visualization Export
        logger.info("STEP 2/2: Generating Visual Reports (HTML & PNG)...")
        viz_cmd = [
            "uv", "run", "scripts/visualize_results.py",
            "--year", str(year),
            "--event", event
        ]
        subprocess.run(viz_cmd, check=True)

        logger.info("=" * 60)
        logger.info(f"PIPELINE SUCCESSFUL: {event} results are ready.")
        logger.info("=" * 60)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Pipeline failed during execution of: {' '.join(e.cmd)}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 2026 Prediction Pipeline Orchestrator")
    parser.add_argument("--year", type=int, default=2026, help="Season year (default: 2026)")
    parser.add_argument("--round", type=int, required=True, help="Round number of the GP")
    parser.add_argument("--event", type=str, required=True, help="Full event name (e.g., 'Miami Grand Prix')")
    parser.add_argument("--log-level", default="INFO", help="Logging verbosity")

    args = parser.parse_args()
    
    # Configure logging for the main orchestrator
    configure_root_pipeline_logger(level=args.log_level)
    
    run_full_pipeline(year=args.year, round_num=args.round, event=args.event)
