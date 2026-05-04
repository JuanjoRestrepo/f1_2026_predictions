import fastf1
from f1_predictions.utils.config import get_settings

settings = get_settings()
fastf1.Cache.enable_cache(str(settings.fastf1_cache_dir))

year = 2026
round_num = 4

print(f"Checking data for {year} Round {round_num}...")
try:
    session = fastf1.get_session(year, round_num, 'R')
    session.load(laps=True, telemetry=False, weather=False, messages=False)
    print("Session results loaded:")
    print(session.results[['Abbreviation', 'ClassifiedPosition', 'GridPosition', 'Status']])
    print(f"Number of laps loaded: {len(session.laps)}")
except Exception as e:
    print(f"Error: {e}")
