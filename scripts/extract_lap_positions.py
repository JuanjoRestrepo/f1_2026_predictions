"""Extract lap-by-lap position data for the Race Timeline Position Chart.

Generates a JSON file with each driver's position on every lap,
used by the Next.js dashboard to render the interactive chart.
"""

import argparse
import json
import logging
from pathlib import Path

import fastf1
import pandas as pd
from dotenv import load_dotenv

from f1_predictions.utils.config import get_settings

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Official 2026 team colors (hex)
TEAM_COLORS: dict[str, str] = {
    "Mercedes": "#00d2be",
    "Ferrari": "#dc0000",
    "McLaren": "#ff8700",
    "Red Bull Racing": "#0600ef",
    "Aston Martin": "#006f62",
    "Alpine": "#0090ff",
    "Williams": "#005aff",
    "Racing Bulls": "#4e7c9b",
    "Haas": "#b6babd",
    "Audi": "#a5a5a5",
}


def extract_lap_positions(year: int, event_name: str, round_num: int) -> dict | None:
    """Extract lap-by-lap position data for all drivers.

    Args:
        year: Championship year.
        event_name: Official FastF1 event name.
        round_num: Round number for output file naming.

    Returns:
        Dict with drivers list and lap-by-lap position matrix.
    """
    settings = get_settings()
    fastf1.Cache.enable_cache(str(settings.fastf1_cache_dir))

    logger.info("Loading race session: %s %d...", event_name, year)
    try:
        session = fastf1.get_session(year, event_name, "R")
        session.load(laps=True, telemetry=False, weather=False, messages=False)
    except Exception as e:
        logger.error("Failed to load session: %s", e)
        return None

    laps = session.laps
    if laps.empty:
        logger.error("No lap data available.")
        return None

    # Get unique drivers sorted by final finishing position
    results = session.results.sort_values("ClassifiedPosition")
    top_drivers = results["Abbreviation"].dropna().tolist()[:10]  # Top 10 only for clarity

    # Build position per lap matrix
    max_lap = int(laps["LapNumber"].max())
    drivers_data = []

    for driver_abbr in top_drivers:
        driver_laps = laps.pick_drivers(driver_abbr).sort_values("LapNumber")
        if driver_laps.empty:
            continue

        # Get team info
        team = driver_laps["Team"].iloc[0] if "Team" in driver_laps.columns else "Unknown"
        color = TEAM_COLORS.get(str(team), "#888888")

        # Build position sequence
        lap_positions: dict[int, int] = {}
        for _, lap_row in driver_laps.iterrows():
            lap_num = int(lap_row["LapNumber"])
            pos = lap_row.get("Position")
            if pd.notna(pos):
                lap_positions[lap_num] = int(pos)

        drivers_data.append({
            "driver": driver_abbr,
            "team": str(team),
            "color": color,
            "positions": lap_positions,
        })

    output = {
        "event": event_name,
        "year": year,
        "total_laps": max_lap,
        "drivers": drivers_data,
    }

    # Save to reports
    out_path = Path(f"reports/{year}/summaries/lap_positions_round_{round_num}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    logger.info("Saved lap positions to %s", out_path)
    return output


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Extract lap-by-lap position data.")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--event", type=str, default="Miami Grand Prix")
    parser.add_argument("--round", type=int, default=4)
    args = parser.parse_args()

    result = extract_lap_positions(args.year, args.event, args.round)
    if result:
        logger.info(
            "Extracted positions for %d drivers over %d laps.",
            len(result["drivers"]),
            result["total_laps"],
        )


if __name__ == "__main__":
    main()
