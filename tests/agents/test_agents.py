from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from f1_predictions.agents.aero_agent import run_aero_agent
from f1_predictions.agents.coordinator_agent import coordinator_agent_run
from f1_predictions.agents.strategy_agent import run_strategy_agent
from f1_predictions.agents.weather_agent import run_weather_agent


@pytest.fixture
def mock_agent_context() -> Generator[
    tuple[MagicMock, MagicMock, MagicMock, MagicMock], None, None
]:
    with (
        patch("f1_predictions.agents.aero_agent.Agent") as mock_aero,
        patch("f1_predictions.agents.strategy_agent.Agent") as mock_strat,
        patch("f1_predictions.agents.weather_agent.Agent") as mock_weather,
        patch("f1_predictions.agents.coordinator_agent.Agent") as mock_coord,
    ):
        yield (mock_aero, mock_strat, mock_weather, mock_coord)


@pytest.mark.asyncio
async def test_aero_agent(
    mock_agent_context: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_aero = mock_agent_context[0]

    agent_instance = AsyncMock()
    mock_aero.return_value.__aenter__.return_value = agent_instance

    chat_resp = AsyncMock()
    chat_resp.structured_output.return_value = {
        "drs_activation_efficiency": "High",
        "downforce_proxy": "Med",
        "speed_trap_analysis": "Top",
        "narrative": "Aero is good",
    }
    agent_instance.chat.return_value = chat_resp

    res = await run_aero_agent("data")
    assert res.narrative == "Aero is good"


@pytest.mark.asyncio
async def test_strategy_agent(
    mock_agent_context: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_strat = mock_agent_context[1]

    agent_instance = AsyncMock()
    mock_strat.return_value.__aenter__.return_value = agent_instance

    chat_resp = AsyncMock()
    chat_resp.structured_output.return_value = {
        "undercut_window": "Lap 15",
        "stint_length_optimization": "Optimal",
        "sc_probability_impact": "High",
        "narrative": "Strat is good",
    }
    agent_instance.chat.return_value = chat_resp

    res = await run_strategy_agent("data", "circuit_info")
    assert res.narrative == "Strat is good"


@pytest.mark.asyncio
async def test_weather_agent(
    mock_agent_context: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_weather = mock_agent_context[2]

    agent_instance = AsyncMock()
    mock_weather.return_value.__aenter__.return_value = agent_instance

    chat_resp = AsyncMock()
    chat_resp.structured_output.return_value = {
        "rain_probability_confidence": "Low",
        "historical_wet_race_outcomes": "Rare",
        "intermediate_tyre_window": "None",
        "narrative": "Dry race",
    }
    agent_instance.chat.return_value = chat_resp

    res = await run_weather_agent("data")
    assert res.narrative == "Dry race"


@pytest.mark.asyncio
async def test_coordinator_agent(
    mock_agent_context: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_aero, mock_strat, mock_weather, mock_coord = mock_agent_context

    # Mock all specialists to return valid data
    for mock_cls in [mock_aero, mock_strat, mock_weather, mock_coord]:
        agent_instance = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = agent_instance

        chat_resp = AsyncMock()
        chat_resp.structured_output.return_value = {
            "drs_activation_efficiency": "High",
            "downforce_proxy": "Med",
            "speed_trap_analysis": "Top",
            "narrative": "Component narrative",
            "undercut_window": "Lap 15",
            "stint_length_optimization": "Optimal",
            "sc_probability_impact": "High",
            "rain_probability_confidence": "Low",
            "historical_wet_race_outcomes": "Rare",
            "intermediate_tyre_window": "None",
            "executive_summary": "Sum",
            "aero_insights": "Aero",
            "strategy_insights": "Strat",
            "weather_insights": "Weather",
            "unified_narrative": "Unified narrative",
            "final_recommendation": "Go fast",
        }
        agent_instance.chat.return_value = chat_resp

    res = await coordinator_agent_run("tel", "circ", "weather")
    assert "Go fast" in res

    # Test fallback if no structured output
    for mock_cls in [mock_aero, mock_strat, mock_weather, mock_coord]:
        agent_instance = mock_cls.return_value.__aenter__.return_value
        agent_instance.chat.return_value.structured_output.return_value = None

    res_fail = await coordinator_agent_run("tel", "circ", "weather")
    assert "Failed to synthesize" in res_fail
