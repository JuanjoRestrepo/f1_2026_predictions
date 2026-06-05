import argparse
import asyncio
import os

import requests

from f1_predictions.live.live_timing import LiveTimingMonitor, PaceAlert
from f1_predictions.utils.logging_setup import (
    configure_root_pipeline_logger,
    get_logger,
)

logger = get_logger(__name__)


def send_discord_alert(alert: PaceAlert) -> None:
    webhook_url = os.environ.get("F1_DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("F1_DISCORD_WEBHOOK_URL not set, skipping Discord alert.")
        return

    emoji = "🚀" if alert.delta < 0 else "🐌"
    msg = (
        f"{emoji} **PACE ALERT**: {alert.driver} on lap {alert.lap} is "
        f"{'faster' if alert.delta < 0 else 'slower'} by **{abs(alert.delta):.2f}s**\n"
        f"*(Predicted: {alert.predicted:.2f}s, Actual: {alert.actual:.2f}s)*"
    )

    try:
        requests.post(webhook_url, json={"content": msg}, timeout=5)
    except Exception:
        logger.exception("Failed to send webhook")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Live Timing Pace Monitor")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--replay", type=str, help="Path to FastF1 replay text file")
    args = parser.parse_args()

    configure_root_pipeline_logger()
    logger.info("Starting F1 Live Pace Monitor for %d Round %d", args.year, args.round)

    monitor = LiveTimingMonitor(replay_file=args.replay)
    async for alert in monitor.run():
        logger.info("ALERT: %s L%d Delta: %+.2fs", alert.driver, alert.lap, alert.delta)
        send_discord_alert(alert)


if __name__ == "__main__":
    asyncio.run(main())
