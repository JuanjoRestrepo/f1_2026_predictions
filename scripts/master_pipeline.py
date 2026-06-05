import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import fastf1
import fastf1.core
import numpy as np
from google import genai

from f1_predictions.features.external_weather import (
    RISK_MIXED,
    RISK_WET,
    WeatherIntelligence,
    build_weather_intelligence,
)
from f1_predictions.ingestion.weather_api import get_forecast
from f1_predictions.utils.circuit_config import get_circuit_config
from f1_predictions.utils.cloud_cache import download_cache, upload_cache
from f1_predictions.utils.config import Settings, get_settings
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

# Config
REPORTS_BASE = Path("reports")
SUMMARY_SUBDIR = "summaries"
DEFAULT_GEMINI_DELAY_SECONDS = 10

logger = get_logger(__name__)

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
    "Cadillac": "#ffffff",
}


def setup_fastf1(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))


def setup_gemini(settings: Settings) -> genai.Client | None:
    api_key = settings.gemini_api_key
    if not api_key:
        logger.warning(
            "F1_GEMINI_API_KEY is not configured; AI narratives will use fallback copy."
        )
        return None
    return genai.Client(api_key=api_key)


def get_gemini_model_sequence(settings: Settings) -> list[str]:
    """Return the configured Gemini primary/fallback sequence without duplicates."""
    model_names = [settings.gemini_model, settings.gemini_fallback_model]
    sequence: list[str] = []
    for model_name in model_names:
        if model_name and model_name not in sequence:
            sequence.append(model_name)
    return sequence


def get_race_info(year: int, round_num: int) -> dict[str, str]:
    """Dynamically discover event info using FastF1 schedule."""
    schedule = fastf1.get_event_schedule(year)
    # FastF1 schedule uses 1-based indexing for rounds.
    # Note: Pre-season testing is usually Round 0.
    event = schedule[schedule["RoundNumber"] == round_num]
    if event.empty:
        return {"name": f"Round {round_num}", "dir": f"Round_{round_num}"}

    event_name = event["EventName"].iloc[0]
    safe_name = event_name.replace(" ", "_")
    event_date = event["EventDate"].iloc[0]
    return {
        "name": event_name,
        "dir": safe_name,
        "event_date": str(event_date.date()),
    }


def save_artifact(
    data: Any, filename: str, year: int, event_dir: str, is_json: bool = True
) -> None:
    summary_path = REPORTS_BASE / str(year) / SUMMARY_SUBDIR / filename
    event_path = REPORTS_BASE / str(year) / event_dir / "results" / filename
    for p in [summary_path, event_path]:
        p.parent.mkdir(parents=True, exist_ok=True)
        if is_json:
            with p.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        else:
            with p.open("w", encoding="utf-8") as f:
                f.write(data)


def _weather_prompt_context(weather: WeatherIntelligence) -> str:
    """Format external weather intelligence for concise AI prompt grounding."""
    if weather.race_day is None:
        return f"WEATHER INTELLIGENCE: {weather.summary}"
    race_day = weather.race_day
    rain = (
        "unknown"
        if weather.rain_probability is None
        else f"{weather.rain_probability:.0%}"
    )
    air_temp = (
        "unknown"
        if race_day.air_temp_c is None
        else f"{race_day.air_temp_c:.1f}C"
    )
    humidity = (
        "unknown"
        if race_day.humidity_pct is None
        else f"{race_day.humidity_pct:.0f}%"
    )
    wind = (
        "unknown"
        if race_day.wind_speed_mps is None
        else f"{race_day.wind_speed_mps:.1f}m/s"
    )
    return (
        "WEATHER INTELLIGENCE: "
        f"provider={weather.provider}, risk={weather.risk_level}, "
        f"rain_probability={rain}, air_temp={air_temp}, "
        f"humidity={humidity}, wind={wind}. {weather.summary}"
    )


def _predicted_weather_strategy_stints(
    total_laps: int,
    weather: WeatherIntelligence,
    compound_colors: dict[str, str],
) -> list[dict[str, Any]]:
    """Return a weather-aware baseline stint plan for predicted strategy JSON."""
    if weather.risk_level == RISK_WET:
        inter_laps = max(1, round(total_laps * 0.3))
        medium_laps = max(1, round(total_laps * 0.35))
        hard_laps = max(1, total_laps - inter_laps - medium_laps)
        return [
            {
                "stint": 1,
                "compound": "INTERMEDIATE",
                "laps": inter_laps,
                "color": compound_colors["INTERMEDIATE"],
            },
            {
                "stint": 2,
                "compound": "MEDIUM",
                "laps": medium_laps,
                "color": compound_colors["MEDIUM"],
            },
            {
                "stint": 3,
                "compound": "HARD",
                "laps": hard_laps,
                "color": compound_colors["HARD"],
            },
        ]
    if weather.risk_level == RISK_MIXED:
        medium_laps = max(1, round(total_laps * 0.35))
        hard_laps = max(1, total_laps - medium_laps)
        return [
            {
                "stint": 1,
                "compound": "MEDIUM",
                "laps": medium_laps,
                "color": compound_colors["MEDIUM"],
            },
            {
                "stint": 2,
                "compound": "HARD",
                "laps": hard_laps,
                "color": compound_colors["HARD"],
            },
        ]

    medium_laps = round(total_laps * 0.4)
    hard_laps = total_laps - medium_laps
    return [
        {
            "stint": 1,
            "compound": "MEDIUM",
            "laps": medium_laps,
            "color": compound_colors["MEDIUM"],
        },
        {
            "stint": 2,
            "compound": "HARD",
            "laps": hard_laps,
            "color": compound_colors["HARD"],
        },
    ]


def generate_lap_data(
    session: fastf1.core.Session, all_drivers: list[str], total_laps: int
) -> dict[str, Any]:
    drivers_lap_list = []
    laps = session.laps

    # Track assigned styles per team to differentiate teammates
    team_driver_count: dict[str, int] = {}

    for drv in all_drivers:
        drv_laps = laps.pick_drivers(drv)
        if drv_laps.empty:
            continue

        team_name = drv_laps["Team"].iloc[0]
        team_driver_count[team_name] = team_driver_count.get(team_name, 0) + 1

        # Pro F1 Tip: Use dashed lines for the 2nd driver of a team
        line_style = "solid" if team_driver_count[team_name] == 1 else "dashed"

        pos_dict = {}
        for lap in range(1, total_laps + 1):
            lap_row = drv_laps[drv_laps["LapNumber"] == lap]
            if not lap_row.empty and not np.isnan(lap_row["Position"].iloc[0]):
                pos_dict[str(lap)] = int(lap_row["Position"].iloc[0])
            else:
                pos_dict[str(lap)] = 22  # DNF Drop

        # Sync final lap
        res_row = session.results[session.results["Abbreviation"] == drv]
        if not res_row.empty:
            off_pos = res_row["Position"].iloc[0]
            pos_dict[str(total_laps)] = int(off_pos) if not np.isnan(off_pos) else 22

        drivers_lap_list.append(
            {
                "driver": drv,
                "team": team_name,
                "color": TEAM_COLORS.get(team_name, "#888888"),
                "lineStyle": line_style,
                "positions": pos_dict,
            }
        )

    return {
        "event": session.event["EventName"],
        "year": session.event["EventDate"].year,
        "total_laps": total_laps,
        "drivers": drivers_lap_list,
    }


def generate_predicted_lap_data(
    session: fastf1.core.Session,
    all_drivers: list[str],
    total_laps: int,
    predicted_order: list[str],
) -> dict[str, Any]:
    import pandas as pd

    drivers_lap_list = []
    team_driver_count: dict[str, int] = {}
    for drv in all_drivers:
        # Default values for pre-race
        team_name = "TBD"
        color = "#888888"
        line_style = "solid"
        start_pos = 20

        # Try to get real data if available
        try:
            if not session.laps.empty:
                drv_laps = session.laps.pick_drivers(drv)
                if not drv_laps.empty:
                    team_name = drv_laps["Team"].iloc[0]
                    team_driver_count[team_name] = (
                        team_driver_count.get(team_name, 0) + 1
                    )
                    line_style = (
                        "solid" if team_driver_count[team_name] == 1 else "dashed"
                    )
                    color = TEAM_COLORS.get(team_name, "#888888")

            if not session.results.empty:
                res_row = session.results[session.results["Abbreviation"] == drv]
                if (
                    not res_row.empty
                    and not pd.isna(res_row["GridPosition"].iloc[0])
                    and int(res_row["GridPosition"].iloc[0]) > 0
                ):
                    start_pos = int(res_row["GridPosition"].iloc[0])
        except Exception as e:
            logger.debug("Could not get grid pos for %s: %s", drv, e)

        end_pos = predicted_order.index(drv) + 1 if drv in predicted_order else 20

        pos_dict = {}
        for lap in range(1, total_laps + 1):
            progress = lap / total_laps
            curr_pos = round(start_pos + (end_pos - start_pos) * progress)
            pos_dict[str(lap)] = curr_pos

        drivers_lap_list.append(
            {
                "driver": drv,
                "team": team_name,
                "color": color,
                "lineStyle": line_style,
                "positions": pos_dict,
            }
        )
    return {
        "event": session.event["EventName"],
        "year": session.event["EventDate"].year,
        "total_laps": total_laps,
        "drivers": drivers_lap_list,
    }


def call_ai_with_retry(
    prompt: str,
    model: genai.Client | None,
    model_names: Sequence[str],
    retries: int = 2,
    delay: int = DEFAULT_GEMINI_DELAY_SECONDS,
) -> str | None:
    import time

    if not model:
        return None

    for model_name in model_names:
        for i in range(retries + 1):
            try:
                response = model.models.generate_content(
                    model=model_name, contents=prompt
                )
                if response.text:
                    logger.info("Gemini narrative generated with model %s.", model_name)
                    return response.text
                logger.warning(
                    "Gemini model %s returned an empty response.", model_name
                )
                break
            except Exception as e:
                if i < retries:
                    logger.warning(
                        "Gemini call failed for %s. Retrying in %ss (%s)",
                        model_name,
                        delay,
                        e,
                    )
                    if delay > 0:
                        time.sleep(delay)
                else:
                    logger.warning(
                        "Gemini model %s failed after retries: %s", model_name, e
                    )
    return None


def main() -> None:
    settings = get_settings()
    configure_root_pipeline_logger(level=settings.log_level)
    parser = argparse.ArgumentParser(
        description="Professional F1 2026 Prediction Pipeline"
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--round", type=int, help="Round number (auto-detected if omitted)"
    )
    parser.add_argument(
        "--auto", action="store_true", help="Run in non-interactive mode (for CI/CD)"
    )
    parser.add_argument(
        "--mode",
        choices=["manual", "forecast", "audit"],
        default="manual",
        help="Execution mode for intelligent schedule detection",
    )
    parser.add_argument(
        "--use-cloud-cache",
        action="store_true",
        help=(
            "Download FastF1 cache from Supabase S3 before run and upload after. "
            "Requires SUPABASE_S3_* environment variables. "
            "Eliminates cold-start re-download latency on serverless workers."
        ),
    )
    args = parser.parse_args()

    # ── Cloud cache pre-run download ─────────────────────────────────────────
    # Download the persisted FastF1 cache from Supabase before enabling it
    # locally. This warms FastF1's cache so session data is served from disk
    # rather than re-downloaded from the FastF1 CDN on every serverless run.
    # Skipped when --use-cloud-cache is not set (local dev / standard CI).
    if args.use_cloud_cache:
        logger.info("Cloud cache: downloading pre-run cache from Supabase S3...")
        download_cache(settings.fastf1_cache_dir)

    setup_fastf1(settings.fastf1_cache_dir)

    import sys

    if args.mode == "forecast":
        from f1_predictions.utils.race_detector import detect_upcoming_race

        race = detect_upcoming_race(args.year, days_ahead=4)
        if not race:
            logger.info(
                "Forecast Mode: No upcoming race this weekend. Exiting cleanly."
            )
            sys.exit(0)
        args.round = race["round"]
    elif args.mode == "audit":
        from f1_predictions.utils.race_detector import detect_last_race

        race = detect_last_race(args.year, days_back=3)
        if not race:
            logger.info(
                "Audit Mode: No recently completed race to analyze. Exiting cleanly."
            )
            sys.exit(0)
        args.round = race["round"]
    elif args.round is None:
        logger.info(
            "Manual Mode: No round specified. Attempting fallback auto-detection..."
        )
        from datetime import datetime

        schedule = fastf1.get_event_schedule(args.year)
        now = datetime.now()
        future_races = schedule[schedule["EventDate"] >= now]
        if not future_races.empty:
            args.round = int(future_races.iloc[0]["RoundNumber"])
            logger.info(
                "Detected next race: %s (Round %d)",
                future_races.iloc[0]["EventName"],
                args.round,
            )
        else:
            args.round = int(schedule["RoundNumber"].max())
            logger.info(
                "No future races found. Defaulting to final round: %d", args.round
            )

    logger.info(
        "Starting Autonomous F1 Intelligence Sync: %d Round %d", args.year, args.round
    )

    ai_model = setup_gemini(settings)
    ai_model_names = get_gemini_model_sequence(settings)
    race_info = get_race_info(args.year, args.round)
    weather_intelligence = build_weather_intelligence(
        settings=settings,
        event_name=race_info["name"],
        target_date=race_info.get("event_date"),
    )
    save_artifact(
        weather_intelligence.as_dict(),
        f"weather_intelligence_round_{args.round}.json",
        args.year,
        race_info["dir"],
    )
    logger.info("External weather intelligence: %s", weather_intelligence.summary)
    session = fastf1.get_session(args.year, args.round, "R")

    # Pre-race safety: On Friday, laps/results aren't available yet.
    # We load metadata first to see if we can proceed with a full sync.
    try:
        session.load(laps=True, telemetry=False, weather=False)
        is_post_race = not session.laps.empty
    except Exception as e:
        logger.info("Post-race data not yet available (expected on Friday): %s", e)
        session.load(laps=False, telemetry=False, weather=False)
        is_post_race = False

    # ── External weather override (pre-race forecast mode) ────────────────────
    # When running pre-race (Friday forecast), FastF1 has no historical weather
    # for the upcoming session. We call the free Open-Meteo API to inject
    # AirTemp, TrackTemp, and Rainfall so downstream feature pipelines have
    # real environmental context instead of silent NaN gaps.
    #
    # This override is applied only when is_post_race=False; post-race audit
    # runs always use authoritative FastF1 telemetry weather data.
    external_weather: dict[str, object] | None = None
    if not is_post_race:
        try:
            event_date = session.event["EventDate"]
            # Prefer Location (city) over Country for finer geocoding accuracy
            event_city = str(
                session.event.get("Location", session.event.get("Country", ""))
            )
            date_str = (
                event_date.strftime("%Y-%m-%d")
                if hasattr(event_date, "strftime")
                else str(event_date)[:10]
            )
            logger.info(
                "Pre-race mode: fetching Open-Meteo forecast for %s on %s",
                event_city,
                date_str,
            )
            external_weather = get_forecast(event_city, date_str)
            if external_weather:
                logger.info(
                    "Weather override active: AirTemp=%.1f°C, TrackTemp=%.1f°C, Rainfall=%s",
                    external_weather.get("AirTemp_mean", float("nan")),
                    external_weather.get("TrackTemp_mean", float("nan")),
                    external_weather.get("Rainfall_any", False),
                )
            else:
                logger.warning(
                    "Open-Meteo forecast unavailable for '%s' — weather features will be NaN.",
                    event_city,
                )
        except Exception as exc:
            logger.warning("External weather fetch failed (non-fatal): %s", exc)

    # Load circuit-specific configuration for Monaco-aware modelling.
    # Falls back to sensible defaults for unknown/new circuits.
    circuit_cfg = get_circuit_config(race_info["name"])

    logger.info(
        "Circuit config loaded: %s | laps=%d | overtake_difficulty=%.2f | "
        "type=%s | SC_prob=%.0f%%",
        race_info["name"],
        circuit_cfg.total_laps,
        circuit_cfg.overtake_difficulty,
        circuit_cfg.circuit_type,
        circuit_cfg.safety_car_probability * 100,
    )

    all_drivers = (
        session.results["Abbreviation"].tolist() if not session.results.empty else []
    )
    if not all_drivers:
        try:
            # Attempt 1: Get official entry list from event metadata
            all_drivers = session.event.get_entry_list()["Abbreviation"].tolist()
        except Exception:
            try:
                # Attempt 2: Inherit from the previous race in the same year
                prev_session = fastf1.get_session(args.year, args.round - 1, "R")
                prev_session.load(laps=False, telemetry=False, weather=False)
                all_drivers = prev_session.results["Abbreviation"].tolist()
                logger.info("Inherited driver list from Round %d", args.round - 1)
            except Exception:
                # Attempt 3: Professional 2024/2026 grid fallback
                all_drivers = [
                    "VER",
                    "PER",
                    "LEC",
                    "SAI",
                    "HAM",
                    "RUS",
                    "NOR",
                    "PIA",
                    "ALO",
                    "STR",
                    "GAS",
                    "OCO",
                    "ALB",
                    "SAR",
                    "TSU",
                    "RIC",
                    "BOT",
                    "ZHO",
                    "MAG",
                    "HUL",
                ]

    # Determine lap count: use actual telemetry post-race, circuit config pre-race.
    # Replaces the generic hardcoded fallback of 50 laps, which is wrong for
    # Monaco (78), Belgium (44), Austria (71), etc.
    if is_post_race:
        total_laps = int(session.laps["LapNumber"].max())
    else:
        total_laps = circuit_cfg.total_laps
        logger.info("Pre-race mode: using circuit config lap count: %d", total_laps)

    # 1. Results (Skip if pre-race)
    if is_post_race:
        import pandas as pd

        results_data = []
        for _, r in session.results.iterrows():
            pos = int(r["Position"]) if not pd.isna(r["Position"]) else None
            time_str = ""
            if not pd.isna(r["Time"]):
                ts = r["Time"].total_seconds()
                if pos == 1:
                    h = int(ts // 3600)
                    m = int((ts % 3600) // 60)
                    s = ts % 60
                    time_str = f"{h}:{m:02d}:{s:06.3f}"
                else:
                    time_str = f"+{ts:.3f}s"
            else:
                time_str = (
                    str(r["Status"]) if r["Status"] not in ["Finished", ""] else ""
                )

            results_data.append(
                {
                    "position": pos,
                    "driver": r["Abbreviation"],
                    "team": r["TeamName"],
                    "status": r["Status"],
                    "time": time_str,
                }
            )

        fastest_lap_data = None
        try:
            if not session.laps.empty:
                fl = session.laps.pick_fastest()
                if not fl.empty:
                    fl_driver = fl["Driver"]
                    fl_time = fl["LapTime"].total_seconds()
                    mins = int(fl_time // 60)
                    secs = fl_time % 60
                    time_fmt = f"{mins}:{secs:06.3f}" if mins > 0 else f"{secs:.3f}s"
                    fastest_lap_data = {
                        "driver": fl_driver,
                        "time": time_fmt,
                        "time_s": fl_time,
                    }
        except Exception as e:
            logger.debug("Could not extract fastest lap: %s", e)

        save_artifact(
            {"fastest_lap": fastest_lap_data, "results": results_data},
            f"actual_results_round_{args.round}.json",
            args.year,
            race_info["dir"],
        )

    # 2. Lap Positions (Actual AND Predicted)
    import pandas as pd

    predictions_path = (
        REPORTS_BASE / str(args.year) / race_info["dir"] / "results" / "predictions.csv"
    )
    predicted_order = []
    if predictions_path.exists():
        preds_df = pd.read_csv(predictions_path)
        preds_df = preds_df.sort_values(by="predicted_laptime_xgb_s")
        predicted_order = preds_df["Driver"].tolist()
    else:
        predicted_order = all_drivers

    if is_post_race:
        save_artifact(
            generate_lap_data(session, all_drivers, total_laps),
            f"lap_positions_round_{args.round}.json",
            args.year,
            race_info["dir"],
        )

    save_artifact(
        generate_predicted_lap_data(session, all_drivers, total_laps, predicted_order),
        f"predicted_lap_positions_round_{args.round}.json",
        args.year,
        race_info["dir"],
    )

    # 3. Tyre
    def process_tyre_data(
        limit: int = 18, is_predicted: bool = False
    ) -> dict[str, Any]:
        data = []
        compound_colors = {
            "SOFT": "#ef4444",
            "MEDIUM": "#facc15",
            "HARD": "#f8fafc",
            "INTERMEDIATE": "#22c55e",
            "WET": "#3b82f6",
        }
        for drv in all_drivers[:limit]:
            team = "TBD"
            full_name = drv
            stint_info = []

            try:
                if not session.laps.empty:
                    drv_laps = session.laps.pick_drivers(drv)
                    if not drv_laps.empty:
                        team = drv_laps["Team"].iloc[0]
                        stints = (
                            drv_laps[["Stint", "Compound", "LapNumber"]]
                            .groupby(["Stint", "Compound"], sort=False)
                            .count()
                            .reset_index()
                        )
                        res_row = session.results[
                            session.results["Abbreviation"] == drv
                        ]
                        full_name = (
                            res_row["FullName"].iloc[0] if not res_row.empty else drv
                        )
                        stint_info = [
                            {
                                "stint": int(r["Stint"]),
                                "compound": str(r["Compound"]).upper(),
                                "laps": int(r["LapNumber"]),
                                "color": compound_colors.get(
                                    str(r["Compound"]).upper(), "#888888"
                                ),
                            }
                            for _, r in stints.iterrows()
                        ]
            except Exception as e:
                logger.debug("Could not process stint for %s: %s", drv, e)

            data.append(
                {
                    "driver": drv,
                    "fullName": full_name,
                    "team": team,
                    "stints": stint_info,
                }
            )

        if is_predicted:
            if weather_intelligence.risk_level in (RISK_WET, RISK_MIXED):
                predicted_stints = _predicted_weather_strategy_stints(
                    total_laps, weather_intelligence, compound_colors
                )
                strategy_label = "Weather-Adjusted"
                n_stops = len(predicted_stints) - 1
            else:
                strategy = circuit_cfg.typical_strategy
                n_stops = len(strategy) - 1
                base_stint_laps = total_laps // len(strategy)
                remainder = total_laps - base_stint_laps * len(strategy)
                predicted_stints = []
                for i, compound in enumerate(strategy):
                    stint_laps = base_stint_laps + (
                        remainder if i == len(strategy) - 1 else 0
                    )
                    predicted_stints.append(
                        {
                            "stint": i + 1,
                            "compound": compound,
                            "laps": stint_laps,
                            "color": compound_colors.get(compound, "#888888"),
                        }
                    )
                strategy_label = circuit_cfg.strategy_label

            for d in data:
                d["stints"] = [stint.copy() for stint in predicted_stints]

            logger.info(
                "Predicted tyre strategy for %s: %s (%d stop%s, %d laps)",
                race_info["name"],
                strategy_label,
                n_stops,
                "s" if n_stops != 1 else "",
                total_laps,
            )
            data.sort(
                key=lambda x: (
                    predicted_order.index(x["driver"])
                    if x["driver"] in predicted_order
                    else 99
                )
            )

        insight = (
            f"Strategic Intelligence Report: Telemetry analysis of stint-loading and compound degradation for the {session.event['EventName']} is currently being synchronized with AI predictive models. "
            "Full strategic narrative will be available shortly."
        )
        if ai_model:
            logger.info(
                "Generating AI strategy insight (%s) with Gemini models: %s",
                "Predicted" if is_predicted else "Actual",
                ", ".join(ai_model_names),
            )
            stint_summary = ", ".join(
                [
                    f"{d['driver']} ({'-'.join([s['compound'][0] for s in d['stints']])})"
                    for d in data[:5]
                ]
            )
            prompt_type = (
                "predicted optimal strategy"
                if is_predicted
                else "actual post-race strategy analysis"
            )
            # Inject circuit-specific context so Gemini's narrative is
            # technically accurate (critical for Monaco vs. generic circuits).
            circuit_context = (
                f" Circuit characteristics: {circuit_cfg.circuit_type} circuit, "
                f"overtake difficulty {circuit_cfg.overtake_difficulty:.0%}, "
                f"safety car probability {circuit_cfg.safety_car_probability:.0%}, "
                f"pit loss time {circuit_cfg.pit_loss_time_s:.1f}s, "
                f"tyre wear mode: {circuit_cfg.tyre_wear_type}."
            )
            prompt = (
                f"Write a professional 2-sentence F1 strategy intelligence report for the "
                f"{session.event['EventName']} 2026 ({prompt_type}). "
                f"Top 5 drivers stints: {stint_summary}.{circuit_context} "
                f"Be highly analytical like an F1 race engineer. Do not use markdown."
            )
            if is_predicted:
                prompt = f"{prompt} {_weather_prompt_context(weather_intelligence)}"
            res = call_ai_with_retry(
                prompt,
                ai_model,
                ai_model_names,
                retries=settings.gemini_retries,
            )
            if res:
                insight = res

        strategy_label = circuit_cfg.strategy_label
        avg_pit = f"{circuit_cfg.pit_loss_time_s:.1f}s"
        return {
            "gp": session.event["EventName"],
            "year": args.year,
            "total_laps": total_laps,
            "winning_strategy": f"{strategy_label} (1-stop)"
            if not is_predicted
            else (f"AI Weather-Adjusted ({weather_intelligence.risk_level})" if weather_intelligence.risk_level in (RISK_WET, RISK_MIXED) else f"AI Optimal ({strategy_label})"),
            "avg_pit_stop": avg_pit
            if not is_predicted
            else f"{circuit_cfg.pit_loss_time_s + 0.5:.1f}s (Est.)",
            "weather_intelligence": weather_intelligence.as_dict()
            if is_predicted
            else None,
            "proven_strategy_insight": insight,
            "drivers": data,
        }

    if is_post_race:
        save_artifact(
            process_tyre_data(22, is_predicted=False),
            f"tyre_intelligence_round_{args.round}.json",
            args.year,
            race_info["dir"],
        )

    save_artifact(
        process_tyre_data(22, is_predicted=True),
        f"predicted_tyre_intelligence_round_{args.round}.json",
        args.year,
        race_info["dir"],
    )

    # 4. AI Narratives
    if ai_model:
        logger.info(
            "Generating AI reports with Gemini models: %s", ", ".join(ai_model_names)
        )

        # Load SHAP metadata for technical reasoning
        shap_file = (
            REPORTS_BASE
            / str(args.year)
            / race_info["dir"]
            / "results"
            / "shap_metadata.json"
        )
        shap_context = ""
        if shap_file.exists():
            with shap_file.open() as f:
                shap_data = json.load(f)
                shap_context = "\nMODEL EXPLAINABILITY DATA (SHAP):\n"
                for feat, impact in shap_data.items():
                    shap_context += (
                        f"- Feature '{feat}': Relative Impact {impact:.4f}\n"
                    )

        fallback = (
            f"### [STRATEGIC INTELLIGENCE] {session.event['EventName']} Narrative Synthesis Underway\n\n"
            f"Technical analysis of the delta between **Actual Race Telemetry** and **Predictive ML Simulations** for the {session.event['EventName']} is currently being synthesized. "
            "Our engineering team is validating stint-loading data, track-specific degradation curves, and overtake-probability maps. "
            "The full strategic narrative will be published once the cross-verification between real-world results and AI simulations is complete."
        )

        # Build circuit-specific context string for both actual and predicted prompts.
        # This is the key differentiator for Monaco vs. generic circuits.
        circuit_context_for_prompt = (
            f"Circuit profile: {circuit_cfg.circuit_type.upper()} street circuit "
            if circuit_cfg.is_street_circuit
            else f"Circuit profile: {circuit_cfg.circuit_type.upper()} permanent circuit "
        )
        circuit_context_for_prompt += (
            f"| Overtake difficulty: {circuit_cfg.overtake_difficulty:.0%} "
            f"| Safety car probability: {circuit_cfg.safety_car_probability:.0%} "
            f"| Pit loss time: {circuit_cfg.pit_loss_time_s:.1f}s "
            f"| Tyre wear mode: {circuit_cfg.tyre_wear_type} "
            f"| Typical strategy: {circuit_cfg.strategy_label}"
        )

        if is_post_race:
            actual_prompt = (
                f"TECHNICAL RACE ANALYSIS: {session.event['EventName']} 2026. "
                f"Actual Results: {session.results.head(10)[['Abbreviation', 'Position']].to_string()}. "
                f"{shap_context}"
                f"\nCIRCUIT CONTEXT: {circuit_context_for_prompt}\n"
                "\nINSTRUCTIONS:\n"
                "Write a professional, high-level technical breakdown of the race. "
                "Use the SHAP data provided to explain *why* the performance hierarchies shifted (e.g., if 'TrackTemp' has high impact, discuss thermal management). "
                "Factor in the circuit-specific characteristics: on a high-overtake-difficulty circuit like Monaco, emphasise qualifying impact and safety car strategy pivots. "
                "Do not use the phrase 'Expert F1 Analysis' or generic filler. "
                "Structure the report using professional numbered headers (1. Stint Dynamics & Tire Management, 2. Aerodynamic Efficiency & Car Performance, 3. Driver Performance Deltas) "
                "with detailed technical bullet points. Focus on stint dynamics, aerodynamic efficiency, and driver performance deltas."
            )
            report = call_ai_with_retry(
                actual_prompt,
                ai_model,
                ai_model_names,
                retries=settings.gemini_retries,
            )
            save_artifact(
                report or fallback,
                f"report_round_{args.round}.md",
                args.year,
                race_info["dir"],
                False,
            )

        # Load predicted order for the predicted report
        pred_file = (
            REPORTS_BASE
            / str(args.year)
            / race_info["dir"]
            / "results"
            / "predictions.csv"
        )
        pred_results_str = ""
        if pred_file.exists():
            import pandas as pd

            pred_df = pd.read_csv(pred_file).sort_values("predicted_laptime_xgb_s")
            pred_results_str = pred_df.head(10)[
                ["Driver", "predicted_laptime_xgb_s"]
            ].to_string()
        else:
            pred_results_str = "No prediction data available."

        predicted_prompt = (
            f"PREDICTIVE ML SIMULATION ANALYSIS: {session.event['EventName']} 2026. "
            f"AI Simulated Results: {pred_results_str}. "
            f"{shap_context}"
            f"\nCIRCUIT CONTEXT: {circuit_context_for_prompt}\n"
            f"\n{_weather_prompt_context(weather_intelligence)}"
            "\nINSTRUCTIONS:\n"
            "Write a serious, high-level technical breakdown of these simulated results. "
            "Use the provided SHAP importance values to justify the model's predictions. "
            "Explicitly account for rain probability, track temperature, humidity, and wind risk when discussing tyre warm-up, degradation, and stint flexibility. "
            "Factor in the circuit-specific characteristics when explaining predictions: "
            "for high overtake_difficulty circuits, GridPosition should be heavily weighted; "
            "for street circuits, pit_loss_time and safety_car_probability dominate strategy. "
            "Explain how the top features (like Aero_Profile or TireLife) drove the predicted gaps. "
            "Structure the report using professional numbered headers (1. Stint Dynamics & Tire Management, 2. Aerodynamic Efficiency & Car Performance, 3. Driver Performance Deltas) "
            "with detailed technical bullet points. Focus on why the ML model predicted these specific stint dynamics and aerodynamic efficiencies compared to typical expectations."
        )
        pred_report = call_ai_with_retry(
            predicted_prompt,
            ai_model,
            ai_model_names,
            retries=settings.gemini_retries,
        )

        save_artifact(
            pred_report or fallback,
            f"predicted_report_round_{args.round}.md",
            args.year,
            race_info["dir"],
            False,
        )

    logger.info("Round %d fully processed with Pro F1 Styles.", args.round)

    # ── Cloud cache post-run upload ───────────────────────────────────────────
    # Zip and upload the updated FastF1 cache so newly-fetched session data
    # persists for subsequent serverless runs. This is non-fatal: a failed
    # upload means the next run will have a slightly cold cache, not a failure.
    if args.use_cloud_cache:
        logger.info("Cloud cache: uploading post-run cache to Supabase S3...")
        upload_cache(settings.fastf1_cache_dir)


if __name__ == "__main__":
    main()
