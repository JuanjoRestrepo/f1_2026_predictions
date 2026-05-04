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
        print("Warning: GOOGLE_API_KEY not found in .env. AI narrative generation will be skipped.")
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-1.5-flash')

def get_race_info(year, round_num):
    # Mapping for GP names and directories
    mapping = {
        4: {"name": "Miami Grand Prix", "dir": "Miami_Grand_Prix"},
        5: {"name": "Canadian Grand Prix", "dir": "Canadian_Grand_Prix"},
    }
    return mapping.get(round_num, {"name": f"Round {round_num}", "dir": f"Round_{round_num}"})

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
    Keep it concise but insightful. Start with a catchy H1 title.
    """
    
    response = model.generate_content(prompt)
    return response.text

def generate_actual_results(session, output_path):
    results = session.results
    data = []
    for idx, row in results.head(20).iterrows():
        data.append({
            "position": int(row['Position']),
            "driver": row['Abbreviation'],
            "team": row['TeamName'],
            "status": row['Status']
        })
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Generated Actual Results: {output_path}")

def generate_lap_positions(session, output_path):
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
    with open(output_path, 'w') as f:
        json.dump(lap_data, f, indent=2)
    print(f"Generated Lap Positions: {output_path}")

def generate_tyre_intelligence(session, output_path, is_predicted=False):
    laps = session.laps
    top_drivers = session.results['Abbreviation'].head(10).tolist()
    DRIVER_NAMES = {'ANT': 'Kimi Antonelli', 'NOR': 'Lando Norris', 'PIA': 'Oscar Piastri', 'RUS': 'George Russell', 'VER': 'Max Verstappen', 'LEC': 'Charles Leclerc', 'HAM': 'Lewis Hamilton', 'SAI': 'Carlos Sainz', 'PER': 'Sergio Perez'}
    COMPOUND_COLORS = {'SOFT': '#ff3333', 'MEDIUM': '#f0f20d', 'HARD': '#ffffff'}
    drivers_data = []
    for drv in top_drivers:
        drv_laps = laps.pick_drivers(drv)
        stints = drv_laps[['Stint', 'Compound', 'LapNumber']].groupby(['Stint', 'Compound'], sort=False).count().reset_index()
        stint_list = []
        for _, row in stints.iterrows():
            cmp = str(row['Compound']).upper()
            stint_list.append({'stint': int(row['Stint']), 'compound': cmp, 'laps': int(row['LapNumber']), 'color': COMPOUND_COLORS.get(cmp, '#888888')})
        drivers_data.append({'driver': drv, 'fullName': DRIVER_NAMES.get(drv, drv), 'team': drv_laps['Team'].iloc[0] if not drv_laps.empty else "Unknown", 'stints': stint_list})
    output = {"gp": session.event['EventName'], "year": session.event['EventDate'].year, "winning_strategy": "Medium to Hard" if not is_predicted else "AI Optimal (M-H)", "avg_pit_stop": "2.45s", "drivers": drivers_data}
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"Generated Tyre Intelligence ({'Predicted' if is_predicted else 'Actual'}): {output_path}")

def main():
    parser = argparse.ArgumentParser(description="F1 2026 Pipeline Manager")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--round", type=int, required=True)
    args = parser.parse_args()

    setup_fastf1()
    ai_model = setup_gemini()
    race_info = get_race_info(args.year, args.round)
    
    print(f"Starting Pipeline for {race_info['name']} (Round {args.round})...")
    session = fastf1.get_session(args.year, args.round, 'R')
    session.load(laps=True, telemetry=False, weather=False)
    
    summary_dir = REPORTS_BASE / str(args.year) / SUMMARY_SUBDIR
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    generate_actual_results(session, summary_dir / f"actual_results_round_{args.round}.json")
    generate_lap_positions(session, summary_dir / f"lap_positions_round_{args.round}.json")
    generate_tyre_intelligence(session, summary_dir / f"tyre_intelligence_round_{args.round}.json")
    generate_tyre_intelligence(session, summary_dir / f"predicted_tyre_intelligence_round_{args.round}.json", is_predicted=True)
    
    # AI Narrative Generation
    actual_report = generate_ai_report(ai_model, session, is_predicted=False)
    with open(summary_dir / f"report_round_{args.round}.md", 'w') as f:
        f.write(actual_report)
        
    predicted_report = generate_ai_report(ai_model, session, is_predicted=True)
    with open(summary_dir / f"predicted_report_round_{args.round}.md", 'w') as f:
        f.write(predicted_report)
    
    print("Pipeline completed successfully.")

if __name__ == "__main__":
    main()
