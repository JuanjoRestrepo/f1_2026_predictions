"""Virtual race simulation script: predict performance hierarchy for a specific GP."""

import argparse
from pathlib import Path

import pandas as pd

from f1_predictions.models import F1PaceRegressor, LightGBMPaceRegressor
from f1_predictions.models.common import prepare_feature_matrix
from f1_predictions.utils.analysis import build_driver_standings, build_predictions_df
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

logger = get_logger(__name__)


def _enrich_with_track_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Join track characteristics metadata with the main DataFrame.

    Args:
        df: Input DataFrame containing EventName.

    Returns:
        DataFrame enriched with numeric track features.
    """
    settings = get_settings()
    meta_path = settings.data_external_dir / "track_metadata.csv"

    if not meta_path.exists():
        logger.warning(
            "Track metadata not found at %s. Skipping enrichment.", meta_path
        )
        return df

    meta_df = pd.read_csv(meta_path)

    # Encode categorical features numerically for the GBM
    type_map = {"Street": 1, "Permanent": 2, "Hybrid": 3}
    df_map = {"Ultra-Low": 1, "Low": 2, "Medium": 3, "High": 4, "Ultra-High": 5}

    meta_df["TrackType_val"] = meta_df["TrackType"].map(type_map).fillna(0)
    meta_df["DownforceLevel_val"] = meta_df["DownforceLevel"].map(df_map).fillna(0)

    # Merge on EventName (standardised in both files)
    enriched_df = df.merge(
        meta_df[
            [
                "EventName",
                "TrackType_val",
                "DownforceLevel_val",
                "Abrasiveness",
                "FullThrottlePct",
                "AvgSpeed_kph",
                "MaxSpeed_kph",
                "CornerCount",
            ]
        ],
        on="EventName",
        how="left",
    )

    # Fill NaNs for tracks not in metadata
    fill_cols = [
        "TrackType_val",
        "DownforceLevel_val",
        "Abrasiveness",
        "FullThrottlePct",
        "AvgSpeed_kph",
        "MaxSpeed_kph",
        "CornerCount",
    ]
    enriched_df[fill_cols] = enriched_df[fill_cols].fillna(0)

    return enriched_df


def run_race_simulation(
    year: int, round_number: int, event_name: str, lap_number: int = 15
) -> None:
    """Run a virtual race simulation for a specific GP and year.

    Args:
        year: The season year to simulate.
        round_number: The round number of the event.
        event_name: The full name of the Grand Prix.
        lap_number: The hypothetical lap number to simulate (default 15).
    """
    settings = get_settings()
    safe_event = event_name.replace(" ", "_")

    # 1. Load historical/current season data
    data_dir = Path(settings.data_outputs_dir) / "laps"
    # We look for all data up to the current round if possible,
    # but primarily the current season's form.
    gold_files = list(data_dir.glob(f"season={year}/**/*.parquet"))

    if not gold_files:
        logger.error(
            "No data found for season %d in %s. Please ingest previous rounds first.",
            year,
            data_dir,
        )
        return

    df_current = pd.concat([pd.read_parquet(f) for f in gold_files])

    # 2. Calculate driver-specific metrics for current form
    logger.info(
        "Calculating current form for %d season (up to round %d)...",
        year,
        round_number,
    )
    driver_stats = (
        df_current.groupby("Driver")
        .agg(
            {
                "SpeedI1": "median",
                "SpeedI2": "median",
                "SpeedFL": "median",
                "SpeedST": "median",
                "Sector1Time_s": "median",
                "Sector2Time_s": "median",
                "Sector3Time_s": "median",
                "LapTime_s": "median",
                "roll_std_3": "median",
                "delta_roll_pace": "median",
                "tyre_deg_slope": "median",
                "tyre_life_norm": "median",
                "DriverPointsPreRace": "max",
                "TeamPointsPreRace": "max",
                "Team": "first",
            }
        )
        .reset_index()
    )

    # 3. Build simulation scenario (Virtual Lap)
    drivers = driver_stats["Driver"].unique()
    sim_data = []

    for driver in drivers:
        d_info = driver_stats[driver_stats["Driver"] == driver].iloc[0]
        sim_data.append(
            {
                "Season": year,
                "RoundNumber": round_number,
                "EventName": event_name,
                "Driver": driver,
                "Team": d_info["Team"],
                "LapNumber": lap_number,
                "Stint": 1,
                "TyreLife": 10,
                "Compound": "MEDIUM",
                "Position": 5,  # Assume a neutral mid-pack position for pace comparison
                "DriverPointsPreRace": d_info["DriverPointsPreRace"],
                "TeamPointsPreRace": d_info["TeamPointsPreRace"],
                "SpeedI1": d_info["SpeedI1"],
                "SpeedI2": d_info["SpeedI2"],
                "SpeedFL": d_info["SpeedFL"],
                "SpeedST": d_info["SpeedST"],
                "Sector1Time_s": d_info["Sector1Time_s"],
                "Sector2Time_s": d_info["Sector2Time_s"],
                "Sector3Time_s": d_info["Sector3Time_s"],
                "roll_laptime_3": d_info["LapTime_s"],
                "roll_laptime_5": d_info["LapTime_s"],
                "roll_std_3": d_info["roll_std_3"],
                "delta_roll_pace": d_info["delta_roll_pace"],
                "tyre_deg_slope": d_info["tyre_deg_slope"],
                "tyre_life_norm": d_info["tyre_life_norm"],
                "PitInTime_s": 0,
                "PitOutTime_s": 0,
                "LapTime_s": 0,  # Target placeholder
            }
        )

    df_sim = pd.DataFrame(sim_data)

    # 4. Train Models on Historical Data (2022 to year-1)
    train_years = list(range(2022, year))
    if not train_years:
        train_years = [2022, 2023, 2024, 2025]  # Fallback

    logger.info("Training models on historical data: %s...", train_years)

    # Load all historical data for training
    gold_all_files = list(data_dir.glob("season=[2-9]*/**/*.parquet"))
    gold_all = pd.concat([pd.read_parquet(f) for f in gold_all_files])
    df_train_full = gold_all[gold_all["Season"].isin(train_years)]

    # ENRICH with track metadata
    logger.info("Enriching training and simulation data with track characteristics...")
    df_train_full = _enrich_with_track_metadata(df_train_full)
    df_sim = _enrich_with_track_metadata(df_sim)

    xgb_model = F1PaceRegressor()
    lgb_model = LightGBMPaceRegressor()

    # Feature matrix alignment
    df_combined = pd.concat([df_train_full, df_sim], ignore_index=True)
    x_all, _ = prepare_feature_matrix(df_combined, require_target=False)

    x_train = x_all.iloc[: -len(drivers)]
    y_train = df_train_full["LapTime_s"]

    # Fit models
    xgb_model.model.fit(x_train.drop(columns=["Season"], errors="ignore"), y_train)
    lgb_model.model.fit(x_train.drop(columns=["Season"], errors="ignore"), y_train)

    # 5. Predict Virtual Lap Results
    logger.info("Running virtual race simulation for %s...", event_name)
    x_sim = x_all.tail(len(drivers)).drop(columns=["Season"], errors="ignore")
    y_pred_xgb = xgb_model.model.predict(x_sim)
    y_pred_lgb = lgb_model.model.predict(x_sim)

    # 6. Save Results
    res_dir = Path(settings.reports_dir) / str(year) / safe_event / "results"
    res_dir.mkdir(parents=True, exist_ok=True)

    metadata = df_sim[["Season", "RoundNumber", "EventName", "Driver", "Team"]]
    predictions_df = build_predictions_df(metadata, y_pred_xgb, y_pred_lgb)

    # Save CSVs
    standings_lgb = build_driver_standings(predictions_df, "predicted_laptime_lgb_s")
    standings_lgb.to_csv(res_dir / "standings.csv", index=False)
    predictions_df.to_csv(res_dir / "predictions.csv", index=False)

    logger.info("Simulation complete! Results saved to: %s", res_dir)
    print(f"\nVirtual Race Prediction for {event_name} ({year}) finished successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a virtual F1 race simulation.")
    parser.add_argument("--year", type=int, default=2026, help="Season year")
    parser.add_argument("--round", type=int, required=True, help="Round number")
    parser.add_argument(
        "--event", type=str, required=True, help="Event name (e.g. 'Miami Grand Prix')"
    )
    parser.add_argument(
        "--lap", type=int, default=15, help="Hypothetical lap number to simulate"
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()
    configure_root_pipeline_logger(level=args.log_level)

    run_race_simulation(
        year=args.year,
        round_number=args.round,
        event_name=args.event,
        lap_number=args.lap,
    )
