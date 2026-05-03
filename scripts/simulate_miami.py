import pandas as pd
import numpy as np
from pathlib import Path
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import get_logger
from f1_predictions.models import F1PaceRegressor, LightGBMPaceRegressor
from f1_predictions.utils.analysis import build_predictions_df, build_driver_standings

logger = get_logger(__name__)

def run_miami_simulation():
    settings = get_settings()
    predict_year = 2026
    
    # 1. Load 2026 data from Hive structure
    data_dir = Path(settings.data_outputs_dir) / "laps"
    gold_files = list(data_dir.glob(f"season={predict_year}/**/*.parquet"))
    if not gold_files:
        logger.error("No data found for 2026 in %s. Please ingest R1-R3 first.", data_dir)
        return
        
    df_2026 = pd.concat([pd.read_parquet(f) for f in gold_files])
    
    # Get latest standing (proxy for Miami starting form)
    latest_points = df_2026.groupby('Driver').agg({
        'DriverPointsPreRace': 'max',
        'TeamPointsPreRace': 'max',
        'Team': 'first'
    }).reset_index()

    # 2. Simulate Miami Laps
    drivers = latest_points['Driver'].unique()
    sim_data = []
    
    for driver in drivers:
        d_info = latest_points[latest_points['Driver'] == driver].iloc[0]
        sim_data.append({
            'Season': 2026,
            'RoundNumber': 4,
            'EventName': 'Miami Grand Prix',
            'Driver': driver,
            'Team': d_info['Team'],
            'LapNumber': 15,
            'Stint': 1,
            'TyreLife': 10,
            'Compound': 'MEDIUM',
            'Position': 5,
            'DriverPointsPreRace': d_info['DriverPointsPreRace'],
            'TeamPointsPreRace': d_info['TeamPointsPreRace'],
            'SpeedI1': df_2026['SpeedI1'].median(),
            'SpeedI2': df_2026['SpeedI2'].median(),
            'SpeedFL': df_2026['SpeedFL'].median(),
            'SpeedST': df_2026['SpeedST'].median(),
            'Sector1Time_s': df_2026['Sector1Time_s'].median(),
            'Sector2Time_s': df_2026['Sector2Time_s'].median(),
            'Sector3Time_s': df_2026['Sector3Time_s'].median(),
            'roll_laptime_3': df_2026['LapTime_s'].median(),
            'roll_laptime_5': df_2026['LapTime_s'].median(),
            'roll_std_3': 0.1,
            'delta_roll_pace': 0.0,
            'tyre_deg_slope': -0.01,
            'tyre_life_norm': 0.2,
            'PitInTime_s': 0,
            'PitOutTime_s': 0,
            'LapTime_s': 0 # Target placeholder
        })
    
    df_sim = pd.DataFrame(sim_data)
    
    # 3. Load Models and Predict
    logger.info("Loading models and running simulation for Miami...")
    
    # Load historical data
    gold_all_files = list(data_dir.glob("season=[2-9]*/**/*.parquet"))
    gold_all = pd.concat([pd.read_parquet(f) for f in gold_all_files])
    
    train_years = [2022, 2023, 2024, 2025]
    
    xgb_model = F1PaceRegressor()
    lgb_model = LightGBMPaceRegressor()
    
    # Feature matrix alignment
    from f1_predictions.models.common import prepare_feature_matrix
    
    # Important: we must align features with the historical training set
    df_train_full = gold_all[gold_all['Season'].isin(train_years)]
    
    # We combine them just to get consistent OHE columns
    df_combined = pd.concat([df_train_full, df_sim], ignore_index=True)
    x_all, _ = prepare_feature_matrix(df_combined)
    
    x_train = x_all.iloc[:-len(drivers)]
    y_train = df_train_full['LapTime_s']
    
    logger.info("Training models on historical data...")
    xgb_model.model.fit(x_train.drop(columns=['Season'], errors='ignore'), y_train)
    lgb_model.model.fit(x_train.drop(columns=['Season'], errors='ignore'), y_train)
    
    # Predict
    x_miami = x_all.tail(len(drivers)).drop(columns=['Season'], errors='ignore')
    y_pred_xgb = xgb_model.model.predict(x_miami)
    y_pred_lgb = lgb_model.model.predict(x_miami)
    
    # 4. Save Results
    res_dir = Path(settings.reports_dir) / str(predict_year) / "Miami_Grand_Prix" / "results"
    res_dir.mkdir(parents=True, exist_ok=True)
    
    miami_metadata = df_sim[['Season', 'RoundNumber', 'EventName', 'Driver', 'Team']]
    predictions_df = build_predictions_df(miami_metadata, y_pred_xgb, y_pred_lgb)
    
    standings_lgb = build_driver_standings(predictions_df, "predicted_laptime_lgb_s")
    standings_lgb.to_csv(res_dir / "standings.csv", index=False)
    predictions_df.to_csv(res_dir / "predictions.csv", index=False)
    
    logger.info("Miami Virtual Race Prediction complete! Saved to: %s", res_dir)

if __name__ == "__main__":
    run_miami_simulation()
