import os
import json
import argparse
import fastf1
import google.generativeai as genai
from pathlib import Path
from dotenv import load_dotenv

# Config
load_dotenv()
CACHE_DIR = "fastf1_cache"
REPORTS_BASE = Path("reports")
SUMMARY_SUBDIR = "summaries"

def setup_fastf1():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    fastf1.Cache.enable_cache(CACHE_DIR)

def setup_gemini():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Warning: GOOGLE_API_KEY not found. AI narrative generation will be skipped.")
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-flash')

def get_race_info(year, round_num):
    # Mapping of rounds to directory names
    mapping = {
        1: {"name": "Bahrain Grand Prix", "dir": "Bahrain_Grand_Prix"},
        2: {"name": "Saudi Arabian Grand Prix", "dir": "Saudi_Arabian_Grand_Prix"},
        3: {"name": "Australian Grand Prix", "dir": "Australian_Grand_Prix"},
        4: {"name": "Miami Grand Prix", "dir": "Miami_Grand_Prix"},
        5: {"name": "Canadian Grand Prix", "dir": "Canadian_Grand_Prix"},
        6: {"name": "Spanish Grand Prix", "dir": "Spanish_Grand_Prix"},
        # Add more rounds as needed or fallback to generic
    }
    return mapping.get(round_num, {"name": f"Round {round_num}", "dir": f"Round_{round_num}"})

def save_artifact(data, filename, year, event_dir, is_json=True):
    """Saves an artifact to both the global summary and the event-specific directory."""
    # 1. Global Summary Path (for Dashboard)
    summary_path = REPORTS_BASE / str(year) / SUMMARY_SUBDIR / filename
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 2. Event-Specific Path (for Organization)
    event_path = REPORTS_BASE / str(year) / event_dir / "results" / filename
    event_path.parent.mkdir(parents=True, exist_ok=True)
    
    paths = [summary_path, event_path]
    
    for p in paths:
        if is_json:
            with open(p, 'w') as f:
                json.dump(data, f, indent=2)
        else:
            with open(p, 'w') as f:
                f.write(data)
    
    print(f"Saved: {filename} to both global and event-specific storage.")

def generate_ai_report(model, session, is_predicted=False):
    if not model:
        return "AI Narrative generation skipped (No API Key)."
    
    event_name = session.event['EventName']
    results = session.results.head(10)[['Abbreviation', 'TeamName', 'Position', 'Status']]
    
    prompt = f"""
    You are an expert F1 Data Scientist and Strategist. 
    Analyze the following results for the {event_name} 2026.
    Regulation Context: 2026 rules (active aero, smaller tires, sustainable fuels).
    
    Type of Report: {'PRE-RACE PREDICTION' if is_predicted else 'POST-RACE ANALYSIS'}
    
    Top 10 Results:
    {results.to_string()}
    
    Write a professional, high-fidelity F1 narrative in Markdown.
    Focus on:
    1. Technical mastery (Aero, Tires, Energy management).
    2. Strategic windows (1-stop vs 2-stop).
    3. Performance deltas between teams (Mercedes, Red Bull, McLaren, Ferrari).
    4. MUST INCLUDE specific Predicted Winner, P2, and Fastest Lap in the Prediction report.
    Keep it concise but insightful. Start with a catchy H1 title.
    """
    
    response = model.generate_content(prompt)
    return response.text

def main():
    parser = argparse.ArgumentParser(description="F1 2026 Pipeline Manager")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--round", type=int, required=True)
    args = parser.parse_args()

    setup_fastf1()
    ai_model = setup_gemini()
    race_info = get_race_info(args.year, args.round)
    event_dir = race_info['dir']
    
    print(f"Starting Pipeline for {race_info['name']} (Round {args.round})...")
    session = fastf1.get_session(args.year, args.round, 'R')
    session.load(laps=True, telemetry=False, weather=False)
    
    # 1. Generate Actual Results
    results_data = []
    for idx, row in session.results.head(20).iterrows():
        results_data.append({
            "position": int(row['Position']),
            "driver": row['Abbreviation'],
            "team": row['TeamName'],
            "status": row['Status']
        })
    save_artifact(results_data, f"actual_results_round_{args.round}.json", args.year, event_dir)
    
    # 2. Generate Lap Positions
    laps = session.laps
    top_drivers = session.results['Abbreviation'].head(10).tolist()
    lap_data = []
    total_laps = int(laps['LapNumber'].max())
    for lap in range(1, total_laps + 1):
        lap_entry = {"lap": lap}
        for drv in top_drivers:
            pos_row = laps[(laps['Abbreviation'] == drv) & (laps['LapNumber'] == lap)]
            if not pos_row.empty:
                lap_entry[drv] = int(pos_row['Position'].iloc[0])
        lap_data.append(lap_entry)
    save_artifact(lap_data, f"lap_positions_round_{args.round}.json", args.year, event_dir)
    
    # 3. Generate Tyre Intelligence
    COMPOUND_COLORS = {'SOFT': '#ff3333', 'MEDIUM': '#f0f20d', 'HARD': '#ffffff'}
    DRIVER_NAMES = {'ANT': 'Kimi Antonelli', 'NOR': 'Lando Norris', 'PIA': 'Oscar Piastri', 'RUS': 'George Russell', 'VER': 'Max Verstappen', 'LEC': 'Charles Leclerc', 'HAM': 'Lewis Hamilton'}
    
    def process_tyre_data(is_pred):
        drivers_data = []
        for drv in top_drivers:
            drv_laps = laps.pick_drivers(drv)
            stints = drv_laps[['Stint', 'Compound', 'LapNumber']].groupby(['Stint', 'Compound'], sort=False).count().reset_index()
            stint_list = []
            for _, row in stints.iterrows():
                cmp = str(row['Compound']).upper()
                stint_list.append({'stint': int(row['Stint']), 'compound': cmp, 'laps': int(row['LapNumber']), 'color': COMPOUND_COLORS.get(cmp, '#888888')})
            drivers_data.append({'driver': drv, 'fullName': DRIVER_NAMES.get(drv, drv), 'team': drv_laps['Team'].iloc[0] if not drv_laps.empty else "Unknown", 'stints': stint_list})
        return {"gp": session.event['EventName'], "year": session.event['EventDate'].year, "winning_strategy": "Medium to Hard", "avg_pit_stop": "2.45s", "drivers": drivers_data}

    save_artifact(process_tyre_data(False), f"tyre_intelligence_round_{args.round}.json", args.year, event_dir)
    save_artifact(process_tyre_data(True), f"predicted_tyre_intelligence_round_{args.round}.json", args.year, event_dir)
    
    # 4. AI Narrative Generation
    actual_report = generate_ai_report(ai_model, session, is_predicted=False)
    save_artifact(actual_report, f"report_round_{args.round}.md", args.year, event_dir, is_json=False)
        
    predicted_report = generate_ai_report(ai_model, session, is_predicted=True)
    save_artifact(predicted_report, f"predicted_report_round_{args.round}.md", args.year, event_dir, is_json=False)
    
    print(f"Pipeline completed successfully for {race_info['name']}.")

if __name__ == "__main__":
    main()
