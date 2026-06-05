"""Coordinator Agent module for orchestrating specialist agents."""

import asyncio

import pydantic
from google.antigravity import Agent, LocalAgentConfig  # type: ignore[import-untyped]

from .aero_agent import run_aero_agent
from .strategy_agent import run_strategy_agent
from .weather_agent import run_weather_agent


class MasterIntelligenceReport(pydantic.BaseModel):
    """Structured master report synthesized from specialist reports."""

    executive_summary: str
    aero_insights: str
    strategy_insights: str
    weather_insights: str
    final_recommendation: str


async def coordinator_agent_run(
    telemetry_data: str, circuit_context: str, weather_context: str
) -> str:
    """Orchestrate specialist agents and synthesize reports."""
    # 1. Spawn specialist subagents in parallel using asyncio.gather
    aero, strategy, weather = await asyncio.gather(
        run_aero_agent(telemetry_data),
        run_strategy_agent(telemetry_data, circuit_context),
        run_weather_agent(weather_context),
    )

    # 2. Coordinator synthesis
    config = LocalAgentConfig(
        response_schema=MasterIntelligenceReport,
        system_instructions=(
            "You are the Race Intelligence Coordinator. You must synthesize "
            "the detailed reports provided by the Aero, Strategy, and Weather "
            "specialists into a cohesive, professional F1 master narrative. "
            "Highlight the key intersections (e.g., how weather impacts the undercut)."
        ),
    )

    async with Agent(config) as agent:
        prompt = (
            f"### Aero Specialist Report\n{aero.model_dump_json(indent=2)}\n\n"
            f"### Strategy Specialist Report\n{strategy.model_dump_json(indent=2)}\n\n"
            f"### Weather Specialist Report\n{weather.model_dump_json(indent=2)}\n\n"
            "Synthesize these into the MasterIntelligenceReport."
        )
        resp = await agent.chat(prompt)
        data = await resp.structured_output()

        if not data:
            return "Failed to synthesize master intelligence report."

        report = MasterIntelligenceReport(**data)

        # Build professional markdown string
        return (
            f"## Master Intelligence Report\n\n"
            f"### Executive Summary\n{report.executive_summary}\n\n"
            f"### Aerodynamic Efficiency\n{report.aero_insights}\n\n"
            f"### Strategic Directives\n{report.strategy_insights}\n\n"
            f"### Weather & Track Conditions\n{report.weather_insights}\n\n"
            f"### Final Recommendation\n{report.final_recommendation}"
        )
