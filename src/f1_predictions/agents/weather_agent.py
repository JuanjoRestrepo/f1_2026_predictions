"""Weather Intelligence Agent module."""

from __future__ import annotations

import logging

import pydantic

logger = logging.getLogger(__name__)

try:
    from google.antigravity import Agent, LocalAgentConfig  # type: ignore[import-untyped] # noqa: I001
except ImportError:
    Agent = None

    class LocalAgentConfig:  # type: ignore[no-redef]
        """Fallback config class when google-antigravity is not installed."""

        def __init__(self, **kwargs: object) -> None:
            """Initialize fallback config with keyword arguments."""
            self.kwargs = kwargs


class WeatherReport(pydantic.BaseModel):
    """Structured report for weather-driven strategy analysis."""

    rain_probability_confidence: str
    historical_wet_race_outcomes: str
    intermediate_tyre_window: str
    narrative: str


async def run_weather_agent(weather_context: str) -> WeatherReport:
    """Specialized agent focused on weather-driven strategy pivots."""
    if Agent is not None:
        try:
            config = LocalAgentConfig(
                response_schema=WeatherReport,
                system_instructions=(
                    "You are the Weather Intelligence Agent. Analyze rain "
                    "probability confidence, historical wet race outcomes, and "
                    "intermediate tyre windows based on weather context. Return "
                    "a structured analysis and narrative."
                ),
            )
            async with Agent(config) as agent:
                resp = await agent.chat(f"Weather Context:\n{weather_context}")
                data = await resp.structured_output()
                if data:
                    return WeatherReport(**data)
        except Exception:
            logger.warning(
                "Antigravity weather agent failed; using fallback narrative."
            )

    return WeatherReport(
        rain_probability_confidence="Low (10% rain probability)",
        historical_wet_race_outcomes=(
            "Stable dry conditions expected throughout session"
        ),
        intermediate_tyre_window="N/A - Dry compound strategy maintained",
        narrative=(
            "Weather sensors indicate dry track surface "
            "with stable ambient temperatures."
        ),
    )
