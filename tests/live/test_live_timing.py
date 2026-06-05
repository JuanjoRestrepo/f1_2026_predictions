import pytest

from f1_predictions.live.live_timing import LiveTimingMonitor


@pytest.mark.asyncio
async def test_live_timing_monitor_replay() -> None:
    monitor = LiveTimingMonitor(replay_file="dummy.txt")
    alerts = []
    async for alert in monitor.run():
        alerts.append(alert)

    assert len(alerts) == 2
    assert alerts[0].driver == "VER"
    assert alerts[1].driver == "LEC"


@pytest.mark.asyncio
async def test_live_timing_monitor_no_replay() -> None:
    monitor = LiveTimingMonitor()
    alerts = []
    async for alert in monitor.run():
        alerts.append(alert)

    assert len(alerts) == 0
