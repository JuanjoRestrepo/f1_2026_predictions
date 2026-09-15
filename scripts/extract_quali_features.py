"""Extract Qualifying session features for the F1 2026 Predictive Pipeline."""

import argparse

import fastf1
import pandas as pd

from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)


def extract_quali_features(
    year: int, round_num: int | str, event_name: str
) -> pd.DataFrame | None:
    """Extract features from the Qualifying session to predict race pace.

    Args:
        year: Championship year.
        round_num: Round number or name.
        event_name: Name of the event for logging context.

    Returns:
        DataFrame containing driver abbreviations, grid positions, and delta to pole.
    """
    settings = get_settings()
    fastf1.Cache.enable_cache(str(settings.fastf1_cache_dir))

    logger.info(
        "Loading Qualifying data for %s (%d) Round %s...", event_name, year, round_num
    )
    try:
        session = fastf1.get_session(year, round_num, "Q")
        session.load(laps=True, telemetry=False, weather=False, messages=False)
    except Exception:
        logger.exception("Failed to load Qualifying session")
        return None

    if session.results is None or session.results.empty:
        logger.error("No results found in Qualifying session.")
        return None

    results = session.results.copy()

    # FastF1 Results for Q session contain Q1, Q2, Q3 times.
    # We want the absolute fastest time set by the driver across the whole session
    # or just use the delta to the pole position.

    # If the session laps object is empty, we must rely on the results table
    if session.laps.empty:
        logger.warning("No lap data available. Using results table only.")
        # Fallback to pure results
        pass

    # Build feature DataFrame
    features = []

    pole_time = pd.NaT
    if not session.laps.empty:
        pole_time_obj = session.laps.pick_fastest()
        if not pole_time_obj.empty and "LapTime" in pole_time_obj and pd.notna(pole_time_obj["LapTime"]):
            pole_time = pole_time_obj["LapTime"]

    # Fallback to minimum time in results table if laps laptime was not found
    if pd.isna(pole_time):
        min_q_secs = float("inf")
        for _, r in results.iterrows():
            for q_sess in ["Q3", "Q2", "Q1"]:
                if q_sess in r and pd.notna(r[q_sess]):
                    ts = r[q_sess].total_seconds() if hasattr(r[q_sess], "total_seconds") else float(r[q_sess])
                    if ts < min_q_secs:
                        min_q_secs = ts
        if min_q_secs < float("inf"):
            pole_time = pd.Timedelta(seconds=min_q_secs)

    field_size = len(results)

    for _, driver_row in results.iterrows():
        driver = driver_row["Abbreviation"]
        team = driver_row["TeamName"]
        pos = driver_row["Position"]

        # Calculate Delta to Pole (in seconds)
        # FastF1 provides Q1, Q2, Q3 columns in results
        best_q_time = pd.NaT
        for q_sess in ["Q3", "Q2", "Q1"]:
            if q_sess in driver_row and pd.notna(driver_row[q_sess]):
                best_q_time = driver_row[q_sess]
                break

        delta_to_pole_s = float("nan")
        quali_gap_pct = float("nan")
        quali_no_time = pd.isna(best_q_time)

        if pd.notna(pole_time) and pd.notna(best_q_time):
            p_sec = pole_time.total_seconds()
            q_sec = best_q_time.total_seconds()
            delta_to_pole_s = q_sec - p_sec
            if p_sec > 0:
                quali_gap_pct = 100.0 * ((q_sec / p_sec) - 1.0)

        grid_norm = (float(pos) - 1.0) / max(1.0, float(field_size) - 1.0) if pd.notna(pos) else 0.5

        features.append(
            {
                "Driver": driver,
                "Team": team,
                "Grid_Position": pos,
                "Quali_Pace_Delta_s": delta_to_pole_s,
                "Grid_Norm": grid_norm,
                "Quali_Gap_Pct": quali_gap_pct,
                "Quali_No_Time": quali_no_time,
            }
        )

    df = pd.DataFrame(features)
    logger.info("Extracted %d driver qualifying features.", len(df))
    return df


def main() -> None:
    """CLI entry point for extracting qualifying features."""
    parser = argparse.ArgumentParser(description="Extract Qualifying features.")
    parser.add_argument("--year", type=int, default=2026, help="Season year")
    parser.add_argument("--round", type=str, default="4", help="Round number")
    parser.add_argument(
        "--event", type=str, default="Miami Grand Prix", help="Event name"
    )

    args = parser.parse_args()

    df = extract_quali_features(args.year, args.round, args.event)
    if df is not None:
        print("\nQualifying Features Preview:")
        print(df.head(10))


if __name__ == "__main__":
    main()
