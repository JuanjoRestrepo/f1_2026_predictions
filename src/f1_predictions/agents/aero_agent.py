"""Aero Intelligence Agent module."""

import pydantic
from google.antigravity import Agent, LocalAgentConfig  # type: ignore[import-untyped]


class AeroReport(pydantic.BaseModel):
    """Structured report for aerodynamic performance analysis."""

    drs_activation_efficiency: str
    downforce_proxy: str
    speed_trap_analysis: str
    narrative: str


async def run_aero_agent(telemetry_data: str) -> AeroReport:
    """Specialized Antigravity agent focused on aerodynamic performance metrics."""
    config = LocalAgentConfig(
        response_schema=AeroReport,
        system_instructions=(
            "You are the Aero Intelligence Agent. Analyze DRS usage, "
            "downforce load proxies, and speed trap rankings from the "
            "provided F1 telemetry data. Return a structured analysis "
            "and a natural language narrative."
        ),
    )
    async with Agent(config) as agent:
        resp = await agent.chat(f"Analyze this telemetry data:\n{telemetry_data}")
        data = await resp.structured_output()
        if data:
            return AeroReport(**data)
        return AeroReport(
            drs_activation_efficiency="N/A",
            downforce_proxy="N/A",
            speed_trap_analysis="N/A",
            narrative="Aero analysis failed to generate a structured response.",
        )
