"""F1 Prediction Pipeline - Master Orchestrator.

This script serves as the main entry point for the entire predictive pipeline.
It orchestrates the virtual race simulation and the subsequent visualization
generation into a single, unified command.

Usage:
    uv run main.py --round 4 --event "Miami Grand Prix"
"""

import argparse
import subprocess
import sys

from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

logger = get_logger(__name__)


def run_full_pipeline(year: int, round_num: int, event: str) -> None:
    """Executes the simulation and visualization scripts sequentially."""
    logger.info("=" * 60)
    logger.info("ORCHESTRATING PIPELINE: %s (%d)", event, year)
    logger.info("=" * 60)

    try:
        # Step 1: Virtual Race Simulation
        logger.info("STEP 1/2: Running Virtual Race Simulation...")
        sim_cmd = [
            "uv",
            "run",
            "scripts/simulate_race.py",
            "--year",
            str(year),
            "--round",
            str(round_num),
            "--event",
            event,
        ]
        subprocess.run(sim_cmd, check=True)  # noqa: S603

        # Step 2: Visualization Export
        logger.info("STEP 2/2: Generating Visual Reports (HTML & PNG)...")
        viz_cmd = [
            "uv",
            "run",
            "scripts/visualize_results.py",
            "--year",
            str(year),
            "--event",
            event,
        ]
        subprocess.run(viz_cmd, check=True)  # noqa: S603

        logger.info("=" * 60)
        logger.info("PIPELINE SUCCESSFUL: %s results are ready.", event)
        logger.info("=" * 60)

    except subprocess.CalledProcessError as e:
        logger.exception("Pipeline failed during execution of: %s", " ".join(e.cmd))
        sys.exit(1)
    except Exception:
        logger.exception("An unexpected error occurred")
        sys.exit(1)


def run_validation_loop(year: int, round_num: int, event: str) -> None:
    """Runs residual analysis and triggers retraining if error is too high."""
    logger.info("=" * 60)
    logger.info("OBSERVABILITY PIPELINE: Validation for %s (%d)", event, year)
    logger.info("=" * 60)

    from scripts.analyze_residuals import run_residual_analysis

    mae = run_residual_analysis(year, round_num, event)

    if mae is None:
        logger.error("Validation failed to complete. Check logs.")
        sys.exit(1)

    mae_threshold = 0.300  # 300ms threshold for F1 pace accuracy

    if mae > mae_threshold:
        logger.warning(
            "MAE (%.3fs) exceeds threshold (%.3fs). TRIGGERING RETRAINING...",
            mae,
            mae_threshold,
        )
        logger.info("Running full pipeline with updated data/weights...")
        run_full_pipeline(year, round_num, event)
    else:
        logger.info(
            "MAE (%.3fs) is within acceptable threshold (%.3fs). No retraining needed.",
            mae,
            mae_threshold,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="F1 2026 Prediction Pipeline Orchestrator"
    )
    parser.add_argument(
        "action",
        choices=["predict", "validate"],
        help=(
            "Action to perform: 'predict' runs the standard simulation pipeline. "
            "'validate' checks past predictions and triggers retraining if needed."
        ),
    )
    parser.add_argument(
        "--year", type=int, default=2026, help="Season year (default: 2026)"
    )
    parser.add_argument(
        "--round", type=int, required=True, help="Round number of the GP"
    )
    parser.add_argument(
        "--event",
        type=str,
        required=True,
        help="Full event name (e.g., 'Miami Grand Prix')",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging verbosity")

    args = parser.parse_args()

    # Configure logging for the main orchestrator
    configure_root_pipeline_logger(level=args.log_level)

    if args.action == "predict":
        run_full_pipeline(year=args.year, round_num=args.round, event=args.event)
    elif args.action == "validate":
        run_validation_loop(year=args.year, round_num=args.round, event=args.event)
