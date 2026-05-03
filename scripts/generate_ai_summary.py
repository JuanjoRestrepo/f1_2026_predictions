"""AI Race Summarizer using Google Gemini.

This script takes the FastF1 race results and our model's predictions,
and generates a journalistic summary of the Grand Prix.
"""

import argparse
import json
import os
import sys

import fastf1
import pandas as pd
from google import genai

from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# F1 Expert System Prompt
SYSTEM_PROMPT = """You are an expert Formula 1 technical journalist and data scientist.
Your job is to analyze the provided JSON telemetry and race results, and write a compelling, 
insightful 3-paragraph summary of the race.

Guidelines:
1. Tone: Professional, analytical, and engaging (like a top-tier motorsport magazine).
2. Content: Focus on the winner's strategy, unexpected podiums, and how the new 2026 
   regulations affected the race pace.
3. Formatting: Use Markdown. Include a bold title.
"""

def generate_summary(year: int, round_num: int | str, event_name: str) -> str | None:
    """Generate an AI summary of the race using Gemini."""
    settings = get_settings()
    
    # Require GEMINI_API_KEY
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable is not set. Cannot run AI Summarizer.")
        return None
        
    fastf1.Cache.enable_cache(str(settings.fastf1_cache_dir))
    
    # 1. Fetch Real Results
    try:
        session = fastf1.get_session(year, round_num, "R")
        session.load(laps=True, telemetry=False, weather=False, messages=False)
    except Exception as e:
        logger.error("Failed to load race session: %s", e)
        return None
        
    if session.results is None or session.results.empty:
        logger.error("No results found for %s %d.", event_name, year)
        return None
        
    results_df = session.results[["Abbreviation", "TeamName", "ClassifiedPosition", "Status", "Points"]].copy()
    top_10 = results_df.head(10).to_dict(orient="records")
    
    # 2. Build Payload
    payload = {
        "event": event_name,
        "year": year,
        "round": round_num,
        "top_10_finishers": top_10,
        "notes": "2026 Regulations: Cars have reduced aerodynamic downforce and smaller tires."
    }
    
    # 3. Call Gemini API
    logger.info("Sending race data to Gemini for analysis...")
    client = genai.Client(api_key=api_key)
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"{SYSTEM_PROMPT}\n\nRace Data:\n{json.dumps(payload, indent=2)}"
        )
        summary = response.text
        logger.info("AI Summary generated successfully.")
        return summary
    except Exception as e:
        logger.error("Gemini API call failed: %s", e)
        return None

def main() -> None:
    """CLI entry point for AI Summarizer."""
    parser = argparse.ArgumentParser(description="Generate AI Race Summary.")
    parser.add_argument("--year", type=int, default=2026, help="Season year")
    parser.add_argument("--round", type=str, default="4", help="Round number")
    parser.add_argument("--event", type=str, default="Miami Grand Prix", help="Event name")

    args = parser.parse_args()
    
    summary = generate_summary(args.year, args.round, args.event)
    if summary:
        print("\n" + "="*80)
        print("🤖 AI RACE REPORT")
        print("="*80 + "\n")
        print(summary)
        print("\n" + "="*80)

if __name__ == "__main__":
    main()
