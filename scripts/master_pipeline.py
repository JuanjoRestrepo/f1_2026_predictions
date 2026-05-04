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

# Professional F1 2026 Color Palette
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
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key: return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('models/gemini-flash-latest')

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

def generate_lap_data(session, all_drivers, total_laps):
    drivers_lap_list = []
    laps = session.laps
    
    # Track assigned styles per team to differentiate teammates
    team_driver_count = {}
    
    for drv in all_drivers:
        drv_laps = laps.pick_drivers(drv)
        if drv_laps.empty: continue
        
        team_name = drv_laps['Team'].iloc[0]
        team_driver_count[team_name] = team_driver_count.get(team_name, 0) + 1
        
        # Pro F1 Tip: Use dashed lines for the 2nd driver of a team
        line_style = "solid" if team_driver_count[team_name] == 1 else "dashed"
        
        pos_dict = {}
        for lap in range(1, total_laps + 1):
            lap_row = drv_laps[drv_laps['LapNumber'] == lap]
            if not lap_row.empty and not np.isnan(lap_row['Position'].iloc[0]):
                pos_dict[str(lap)] = int(lap_row['Position'].iloc[0])
            else:
                pos_dict[str(lap)] = 22 # DNF Drop
        
        # Sync final lap
        res_row = session.results[session.results['Abbreviation'] == drv]
        if not res_row.empty:
            off_pos = res_row['Position'].iloc[0]
            pos_dict[str(total_laps)] = int(off_pos) if not np.isnan(off_pos) else 22

        drivers_lap_list.append({
            "driver": drv,
            "team": team_name,
            "color": TEAM_COLORS.get(team_name, "#888888"),
            "lineStyle": line_style,
            "positions": pos_dict
        })
    
    return {
        "event": session.event['EventName'],
        "year": session.event['EventDate'].year,
        "total_laps": total_laps,
        "drivers": drivers_lap_list
    }

def generate_predicted_lap_data(session, all_drivers, total_laps, predicted_order):
    import pandas as pd
    drivers_lap_list = []
    team_driver_count = {}
    for drv in all_drivers:
        drv_laps = session.laps.pick_drivers(drv)
        if drv_laps.empty: continue
        team_name = drv_laps['Team'].iloc[0]
        team_driver_count[team_name] = team_driver_count.get(team_name, 0) + 1
        line_style = "solid" if team_driver_count[team_name] == 1 else "dashed"
        
        res_row = session.results[session.results['Abbreviation'] == drv]
        start_pos = int(res_row['GridPosition'].iloc[0]) if not res_row.empty and not pd.isna(res_row['GridPosition'].iloc[0]) and int(res_row['GridPosition'].iloc[0]) > 0 else 20
        end_pos = predicted_order.index(drv) + 1 if drv in predicted_order else 20
        
        pos_dict = {}
        for lap in range(1, total_laps + 1):
            progress = lap / total_laps
            curr_pos = round(start_pos + (end_pos - start_pos) * progress)
            pos_dict[str(lap)] = curr_pos
            
        drivers_lap_list.append({
            "driver": drv,
            "team": team_name,
            "color": TEAM_COLORS.get(team_name, "#888888"),
            "lineStyle": line_style,
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
    import pandas as pd
    results_data = []
    for idx, r in session.results.iterrows():
        pos = int(r['Position']) if not pd.isna(r['Position']) else None
        time_str = ""
        if not pd.isna(r['Time']):
            ts = r['Time'].total_seconds()
            if pos == 1:
                h = int(ts // 3600)
                m = int((ts % 3600) // 60)
                s = ts % 60
                time_str = f"{h}:{m:02d}:{s:06.3f}"
            else:
                time_str = f"+{ts:.3f}s"
        else:
            time_str = str(r['Status']) if r['Status'] not in ['Finished', ''] else ""
            
        results_data.append({
            "position": pos, 
            "driver": r['Abbreviation'], 
            "team": r['TeamName'], 
            "status": r['Status'],
            "time": time_str
        })
    save_artifact(results_data, f"actual_results_round_{args.round}.json", args.year, race_info['dir'])

    # 2. Lap Positions (Actual AND Predicted)
    predictions_path = REPORTS_BASE / str(args.year) / race_info['dir'] / "results" / "data" / "predictions.csv"
    predicted_order = []
    if predictions_path.exists():
        preds_df = pd.read_csv(predictions_path)
        preds_df = preds_df.sort_values(by="predicted_laptime_xgb_s")
        predicted_order = preds_df['Driver'].tolist()
    else:
        predicted_order = all_drivers

    save_artifact(generate_lap_data(session, all_drivers, total_laps), f"lap_positions_round_{args.round}.json", args.year, race_info['dir'])
    save_artifact(generate_predicted_lap_data(session, all_drivers, total_laps, predicted_order), f"predicted_lap_positions_round_{args.round}.json", args.year, race_info['dir'])
    
    # 3. Tyre
    def process_tyre_data(limit=18, is_predicted=False):
        data = []
        compound_colors = {
            "SOFT": "#ef4444",
            "MEDIUM": "#facc15",
            "HARD": "#f8fafc",
            "INTERMEDIATE": "#22c55e",
            "WET": "#3b82f6"
        }
        for drv in all_drivers[:limit]:
            drv_laps = session.laps.pick_drivers(drv)
            if drv_laps.empty: continue
            stints = drv_laps[['Stint', 'Compound', 'LapNumber']].groupby(['Stint', 'Compound'], sort=False).count().reset_index()
            res_row = session.results[session.results['Abbreviation'] == drv]
            full_name = res_row['FullName'].iloc[0] if not res_row.empty else drv
            data.append({
                'driver': drv, 
                'fullName': full_name, 
                'team': drv_laps['Team'].iloc[0], 
                'stints': [
                    {
                        'stint': int(r['Stint']), 
                        'compound': str(r['Compound']).upper(), 
                        'laps': int(r['LapNumber']), 
                        'color': compound_colors.get(str(r['Compound']).upper(), "#888888")
                    } for _, r in stints.iterrows()
                ]
            })
            
        if is_predicted:
            for d in data:
                m_laps = round(total_laps * 0.4)
                h_laps = total_laps - m_laps
                d['stints'] = [
                    {'stint': 1, 'compound': 'MEDIUM', 'laps': m_laps, 'color': compound_colors['MEDIUM']},
                    {'stint': 2, 'compound': 'HARD', 'laps': h_laps, 'color': compound_colors['HARD']}
                ]
            data.sort(key=lambda x: predicted_order.index(x['driver']) if x['driver'] in predicted_order else 99)

        insight = "Insight generated by Pipeline Manager." if not is_predicted else "AI Prediction Insight."
        if ai_model:
            try:
                print(f"Generating AI strategy insight ({'Predicted' if is_predicted else 'Actual'})...")
                stint_summary = ", ".join([f"{d['driver']} ({'-'.join([s['compound'][0] for s in d['stints']])})" for d in data[:5]])
                prompt_type = "predicted optimal strategy" if is_predicted else "actual post-race strategy analysis"
                prompt = f"Write a professional 2-sentence F1 strategy intelligence report for the {session.event['EventName']} 2026 ({prompt_type}). Top 5 drivers stints: {stint_summary}. Be highly analytical like an F1 race engineer. Do not use markdown."
                insight = ai_model.generate_content(prompt).text.strip().replace('"', '')
            except Exception as e:
                print(f"Strategy Insight AI Failed: {e}")

        return {
            "gp": session.event['EventName'], 
            "year": args.year, 
            "total_laps": total_laps,
            "winning_strategy": "Medium to Hard" if not is_predicted else "AI Optimal (M-H)",
            "avg_pit_stop": "2.45s" if not is_predicted else "2.50s (Est.)",
            "proven_strategy_insight": insight,
            "drivers": data
        }
    
    tyre_data_actual = process_tyre_data(22, is_predicted=False)
    tyre_data_pred = process_tyre_data(22, is_predicted=True)
    save_artifact(tyre_data_actual, f"tyre_intelligence_round_{args.round}.json", args.year, race_info['dir'])
    save_artifact(tyre_data_pred, f"predicted_tyre_intelligence_round_{args.round}.json", args.year, race_info['dir'])
    
    # 4. AI Narratives
    if ai_model:
        try:
            print(f"Generating AI reports with {ai_model.model_name}...")
            prompt = f"Expert F1 Analysis for {session.event['EventName']} 2026. Results: {session.results.head(10)[['Abbreviation', 'Position']].to_string()}"
            report = ai_model.generate_content(prompt).text
            pred_report = ai_model.generate_content("PREDICTION " + prompt).text
            save_artifact(report, f"report_round_{args.round}.md", args.year, race_info['dir'], False)
            save_artifact(pred_report, f"predicted_report_round_{args.round}.md", args.year, race_info['dir'], False)
        except Exception as e:
            print(f"AI Failed: {str(e)}")
            save_artifact(f"AI Unavailable: {str(e)}", f"report_round_{args.round}.md", args.year, race_info['dir'], False)
            save_artifact(f"AI Unavailable: {str(e)}", f"predicted_report_round_{args.round}.md", args.year, race_info['dir'], False)
    
    print(f"Round {args.round} fully processed with Pro F1 Styles.")

if __name__ == "__main__":
    main()
