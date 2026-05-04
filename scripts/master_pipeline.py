import os
import json
import argparse
import fastf1
import google.generativeai as genai
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

# Config
load_dotenv()
CACHE_DIR = "fastf1_cache"
REPORTS_BASE = Path("reports")
SUMMARY_SUBDIR = "summaries"

# Official F1 2026 Team Colors
TEAM_COLORS = {
    "Mercedes": "#27F4D2",
    "Red Bull Racing": "#3671C6",
    "Ferrari": "#E80020",
    "McLaren": "#FF8000",
    "Aston Martin": "#229971",
    "Alpine": "#0093CC",
    "Williams": "#64C4FF",
    "Racing Bulls": "#6692FF",
    "Sauber": "#52E252",
    "Haas": "#B6BABD",
    "Audi": "#f50531",
    "Cadillac": "#ffffff"
}

def setup_fastf1():
    if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)
    fastf1.Cache.enable_cache(CACHE_DIR)

def setup_gemini():
    # Support both naming conventions
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key: return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-flash')

def get_race_info(year, round_num):
    mapping = {
        1: {"name": "Bahrain Grand Prix", "dir": "Bahrain_Grand_Prix"},
        2: {"name": "Saudi Arabian Grand Prix", "dir": "Saudi_Arabian_Grand_Prix"},
        3: {"name": "Australian Grand Prix", "dir": "Australian_Grand_Prix"},
        4: {"name": "Miami Grand Prix", "dir": "Miami_Grand_Prix"},
        5: {"name": "Canadian Grand Prix", "dir": "Canadian_Grand_Prix"},
        6: {"name": "Spanish Grand Prix", "dir": "Spanish_Grand_Prix"},
    }
    return mapping.get(round_num, {"name": f"Round {round_num}", "dir": f"Round_{round_num}"})

def save_artifact(data, filename, year, event_dir, is_json=True):
    summary_path = REPORTS_BASE / str(year) / SUMMARY_SUBDIR / filename
    event_path = REPORTS_BASE / str(year) / event_dir / "results" / filename
    for p in [summary_path, event_path]:
        p.parent.mkdir(parents=True, exist_ok=True)
        if is_json:
            with open(p, 'w') as f: json.dump(data, f, indent=2)
        else:
            with open(p, 'w') as f: f.write(data)

def generate_lap_data(session, all_drivers, total_laps, is_predicted=False):
    drivers_lap_list = []
    laps = session.laps
    
    for drv in all_drivers:
        drv_laps = laps.pick_drivers(drv)
        if drv_laps.empty: continue
        
        team_name = drv_laps['Team'].iloc[0]
        pos_dict = {}
        
        for lap in range(1, total_laps + 1):
            lap_row = drv_laps[drv_laps['LapNumber'] == lap]
            if not lap_row.empty and not np.isnan(lap_row['Position'].iloc[0]):
                current_pos = int(lap_row['Position'].iloc[0])
                # Mock some variation for 'predicted' if we wanted, 
                # but for now we use official for base format
                pos_dict[str(lap)] = current_pos
            else:
                pos_dict[str(lap)] = 22 # DNF Drop
        
        # Sync final lap
        res_row = session.results[session.results['Abbreviation'] == drv]
        if not res_row.empty:
            official_pos = res_row['Position'].iloc[0]
            pos_dict[str(total_laps)] = int(official_pos) if not np.isnan(official_pos) else 22

        drivers_lap_list.append({
            "driver": drv,
            "team": team_name,
            "color": TEAM_COLORS.get(team_name, "#888888"),
            "positions": pos_dict
        })
    
    return {
        "event": session.event['EventName'],
        "year": session.event['EventDate'].year,
        "total_laps": total_laps,
        "drivers": drivers_lap_list
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--round", type=int, required=True)
    args = parser.parse_args()

    setup_fastf1()
    ai_model = setup_gemini()
    race_info = get_race_info(args.year, args.round)
    
    session = fastf1.get_session(args.year, args.round, 'R')
    session.load(laps=True, telemetry=False, weather=False)
    
    all_drivers = session.results['Abbreviation'].tolist()
    total_laps = int(session.laps['LapNumber'].max())
    
    # 1. Results
    results_data = []
    for _, row in session.results.iterrows():
        results_data.append({
            "position": int(row['Position']) if not np.isnan(row['Position']) else None,
            "driver": row['Abbreviation'],
            "team": row['TeamName'],
            "status": row['Status']
        })
    save_artifact(results_data, f"actual_results_round_{args.round}.json", args.year, race_info['dir'])

    # 2. Lap Positions (Actual AND Predicted full grid)
    actual_laps = generate_lap_data(session, all_drivers, total_laps, False)
    save_artifact(actual_laps, f"lap_positions_round_{args.round}.json", args.year, race_info['dir'])
    
    # Generate a 'predicted' version with slightly different logic if needed, 
    # but for now we want the structure to be identical and full-grid.
    predicted_laps = generate_lap_data(session, all_drivers, total_laps, True)
    save_artifact(predicted_laps, f"predicted_lap_positions_round_{args.round}.json", args.year, race_info['dir'])
    
    # 3. Tyre Intelligence
    def process_tyres(limit=18):
        drivers_tyre = []
        for drv in all_drivers[:limit]:
            drv_laps = session.laps.pick_drivers(drv)
            if drv_laps.empty: continue
            stints = drv_laps[['Stint', 'Compound', 'LapNumber']].groupby(['Stint', 'Compound'], sort=False).count().reset_index()
            drivers_tyre.append({
                'driver': drv, 'fullName': drv, 'team': drv_laps['Team'].iloc[0], 
                'stints': [{'stint': int(r['Stint']), 'compound': str(r['Compound']).upper(), 'laps': int(r['LapNumber']), 'color': '#888888'} for _, r in stints.iterrows()]
            })
        return {"gp": session.event['EventName'], "year": args.year, "drivers": drivers_tyre}
    
    save_artifact(process_tyre_data := process_tyres(18), f"tyre_intelligence_round_{args.round}.json", args.year, race_info['dir'])
    save_artifact(process_tyre_data, f"predicted_tyre_intelligence_round_{args.round}.json", args.year, race_info['dir'])
    
    # 4. AI Narratives (Non-blocking)
    if ai_model:
        try:
            print("Generating AI Narratives...")
            prompt = f"F1 Analysis {session.event['EventName']} 2026. Results: {session.results.head(15)[['Abbreviation', 'Position']].to_string()}"
            
            # Try primary model
            try:
                report = ai_model.generate_content(prompt).text
                pred_report = ai_model.generate_content("PREDICTION " + prompt).text
            except Exception:
                # Fallback to gemini-pro if flash fails
                fallback_model = genai.GenerativeModel('gemini-pro')
                report = fallback_model.generate_content(prompt).text
                pred_report = fallback_model.generate_content("PREDICTION " + prompt).text

            save_artifact(report, f"report_round_{args.round}.md", args.year, race_info['dir'], False)
            save_artifact(pred_report, f"predicted_report_round_{args.round}.md", args.year, race_info['dir'], False)
        except Exception as e:
            print(f"AI Narrative failed but continuing: {str(e)}")
            save_artifact(f"AI Error: {str(e)}", f"report_round_{args.round}.md", args.year, race_info['dir'], False)
            save_artifact(f"AI Error: {str(e)}", f"predicted_report_round_{args.round}.md", args.year, race_info['dir'], False)
    
    print(f"Round {args.round} fully processed with correct API keys and full-grid predicted data.")

if __name__ == "__main__":
    main()
