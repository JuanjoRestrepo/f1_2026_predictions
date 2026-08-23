"""Coordinator Agent module for orchestrating specialist agents."""

from __future__ import annotations

import asyncio
import logging

import pydantic

from .aero_agent import run_aero_agent
from .strategy_agent import run_strategy_agent
from .weather_agent import run_weather_agent

logger = logging.getLogger(__name__)

try:
    from google.antigravity import Agent, LocalAgentConfig  # type: ignore[import-untyped] # noqa: I001

    HAS_ANTIGRAVITY = True
except ImportError:
    HAS_ANTIGRAVITY = False
    Agent = None
    LocalAgentConfig = None


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

    if HAS_ANTIGRAVITY and LocalAgentConfig is not None and Agent is not None:
        try:
            config = LocalAgentConfig(
                response_schema=MasterIntelligenceReport,
                system_instructions=(
                    "You are the Race Intelligence Coordinator. You must synthesize "
                    "the detailed reports provided by the Aero, Strategy, and Weather "
                    "specialists into a cohesive, professional F1 master narrative. "
                    "Highlight key intersections (e.g. how weather impacts undercut)."
                ),
            )
            async with Agent(config) as agent:
                aero_json = aero.model_dump_json(indent=2)
                strat_json = strategy.model_dump_json(indent=2)
                wx_json = weather.model_dump_json(indent=2)
                prompt = (
                    f"### Aero Specialist Report\n{aero_json}\n\n"
                    f"### Strategy Specialist Report\n{strat_json}\n\n"
                    f"### Weather Specialist Report\n{wx_json}\n\n"
                    "Synthesize these into the MasterIntelligenceReport."
                )
                resp = await agent.chat(prompt)
                data = await resp.structured_output()
                if data:
                    report = MasterIntelligenceReport(**data)
                    return (
                        f"## Master Intelligence Report\n\n"
                        f"### Executive Summary\n{report.executive_summary}\n\n"
                        f"### Aerodynamic Efficiency\n{report.aero_insights}\n\n"
                        f"### Strategic Directives\n{report.strategy_insights}\n\n"
                        f"### Weather & Track Conditions\n{report.weather_insights}\n\n"
                        f"### Final Recommendation\n{report.final_recommendation}"
                    )
                return "Failed to synthesize master intelligence report."
        except Exception:
            logger.warning(
                "Coordinator agent failed; using standard fallback synthesis."
            )

    # Standard fallback synthesis if antigravity is not installed or raises an error
    return (
        f"## Master Intelligence Report\n\n"
        f"### Executive Summary\n{aero.narrative}\n\n"
        f"### Aerodynamic Efficiency\n{aero.speed_trap_analysis}\n\n"
        f"### Strategic Directives\n{strategy.narrative}\n\n"
        f"### Weather & Track Conditions\n{weather.narrative}\n\n"
        f"### Final Recommendation\n{strategy.stint_length_optimization}"
    )
