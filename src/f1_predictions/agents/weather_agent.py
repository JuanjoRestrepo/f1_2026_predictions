"""Weather Intelligence Agent module."""

import pydantic
from google.antigravity import Agent, LocalAgentConfig  # type: ignore[import-untyped]


class WeatherReport(pydantic.BaseModel):
    """Structured report for weather-driven strategy analysis."""

    rain_probability_confidence: str
    historical_wet_race_outcomes: str
    intermediate_tyre_window: str
    narrative: str


async def run_weather_agent(weather_context: str) -> WeatherReport:
    """Specialized Antigravity agent focused on weather-driven strategy pivots."""
    config = LocalAgentConfig(
        response_schema=WeatherReport,
        system_instructions=(
            "You are the Weather Intelligence Agent. Analyze rain probability "
            "confidence, historical wet race outcomes, and intermediate tyre "
            "windows based on the provided weather context. Return a structured "
            "analysis and narrative."
        ),
    )
    async with Agent(config) as agent:
        resp = await agent.chat(f"Weather Context:\n{weather_context}")
        data = await resp.structured_output()
        if data:
            return WeatherReport(**data)
        return WeatherReport(
            rain_probability_confidence="N/A",
            historical_wet_race_outcomes="N/A",
            intermediate_tyre_window="N/A",
            narrative="Weather analysis failed to generate a structured response.",
        )
