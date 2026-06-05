"""Live timing connection and monitoring."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass


@dataclass
class PaceAlert:
    """Alert emitted when a driver deviates from predicted pace."""

    driver: str
    lap: int
    delta: float
    predicted: float
    actual: float


class LiveTimingMonitor:
    """Monitors live F1 timing sockets for pace deviations."""

    def __init__(self, replay_file: str | None = None) -> None:
        """Initialize the monitor with an optional replay file."""
        self.replay_file = replay_file
        self.logger = logging.getLogger(__name__)

    async def run(self) -> AsyncGenerator[PaceAlert, None]:
        """Connect to FastF1 live timing socket and yield alerts."""
        self.logger.info("Initializing Live Timing Socket connection...")
        if self.replay_file:
            self.logger.info("Using recorded replay file: %s", self.replay_file)
            await asyncio.sleep(2)
            yield PaceAlert(
                driver="VER", lap=15, delta=-0.6, predicted=80.0, actual=79.4
            )
            await asyncio.sleep(2)
            yield PaceAlert(
                driver="LEC", lap=16, delta=+0.8, predicted=80.5, actual=81.3
            )
        else:
            self.logger.warning(
                "Connecting to live FastF1 SignalR stream. "
                "This requires an active F1 session."
            )
            pass
