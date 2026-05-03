"""Generate synthetic predicted lap-by-lap position data based on ML predictions.

Used to populate the 'Predicted' view of the Race Timeline chart
until Phase 7 (detailed lap-by-lap simulation) is implemented.
"""

import json
import pandas as pd
from pathlib import Path
import random

# Official 2026 team colors (hex)
TEAM_COLORS = {
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

def generate_predicted_timeline(year=2026, round_num=4, event_name="Miami Grand Prix"):
    pred_path = Path(f"reports/{year}/Miami_Grand_Prix/results/predictions.csv")
    if not pred_path.exists():
        print(f"Error: {pred_path} not found")
        return

    df = pd.read_csv(pred_path)
    # Sort by predicted pace to get finishing order
    df = df.sort_values("predicted_laptime_xgb_s").reset_index(drop=True)
    
    top_10 = df.head(10).copy()
    total_laps = 57
    
    # Create a synthetic starting order (shuffle slightly from the finish order)
    drivers = top_10["Driver"].tolist()
    start_order = list(drivers)
    random.seed(42)
    random.shuffle(start_order)
    
    # Map driver to start position
    start_pos_map = {driver: i + 1 for i, driver in enumerate(start_order)}
    finish_pos_map = {driver: i + 1 for i, driver in enumerate(drivers)}
    
    drivers_data = []
    for _, row in top_10.iterrows():
        driver = row["Driver"]
        team = row["Team"]
        color = TEAM_COLORS.get(team, "#888888")
        
        start_p = start_pos_map[driver]
        finish_p = finish_pos_map[driver]
        
        positions = {}
        for lap in range(1, total_laps + 1):
            # Simple linear interpolation with some random noise to make it look 'real'
            progress = (lap - 1) / (total_laps - 1)
            # Add a bit of sine wave to simulate battling
            noise = random.randint(-1, 1) if lap % 5 == 0 else 0
            current_p = int(round(start_p + (finish_p - start_p) * progress + noise))
            # Clamp position between 1 and 20
            current_p = max(1, min(20, current_p))
            positions[lap] = current_p
            
        drivers_data.append({
            "driver": driver,
            "team": team,
            "color": color,
            "positions": positions
        })

    output = {
        "event": event_name,
        "year": year,
        "total_laps": total_laps,
        "drivers": drivers_data
    }

    out_path = Path(f"reports/{year}/summaries/predicted_lap_positions_round_{round_num}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"Generated synthetic predicted timeline: {out_path}")

if __name__ == "__main__":
    generate_predicted_timeline()
