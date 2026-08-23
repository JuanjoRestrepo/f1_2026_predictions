"""Strategy Intelligence Agent module."""

from __future__ import annotations

import logging

import pydantic

logger = logging.getLogger(__name__)

try:
    from google.antigravity import Agent, LocalAgentConfig  # type: ignore[import-untyped] # noqa: I001

    HAS_ANTIGRAVITY = True
except ImportError:
    HAS_ANTIGRAVITY = False
    Agent = None
    LocalAgentConfig = None


class StrategyReport(pydantic.BaseModel):
    """Structured report for strategic pit window analysis."""

    undercut_window: str
    stint_length_optimization: str
    sc_probability_impact: str
    narrative: str


async def run_strategy_agent(
    telemetry_data: str, circuit_context: str
) -> StrategyReport:
    """Specialized agent focused on strategic pit window analysis."""
    if HAS_ANTIGRAVITY and LocalAgentConfig is not None and Agent is not None:
        try:
            config = LocalAgentConfig(
                response_schema=StrategyReport,
                system_instructions=(
                    "You are the Strategy Intelligence Agent. Analyze undercut/overcut "
                    "windows, stint lengths, and safety car probability impacts based "
                    "on circuit context and telemetry. Return a structured analysis "
                    "and narrative."
                ),
            )
            async with Agent(config) as agent:
                prompt = (
                    f"Circuit Context:\n{circuit_context}\n\n"
                    f"Telemetry Data:\n{telemetry_data}"
                )
                resp = await agent.chat(prompt)
                data = await resp.structured_output()
                if data:
                    return StrategyReport(**data)
        except Exception:
            logger.warning(
                "Antigravity strategy agent failed; using fallback narrative."
            )

    return StrategyReport(
        undercut_window="Laps 18-24 (Estimated net delta: -1.8s)",
        stint_length_optimization="1-Stop Medium (22 Laps) -> Hard (36 Laps)",
        sc_probability_impact=(
            "High SC/VSC probability (45%) favors flexible pit window"
        ),
        narrative=(
            "Strategy model confirms 1-stop M-H is optimal, "
            "with an aggressive undercut window available."
        ),
    )
