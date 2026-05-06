"""Notification dispatcher for the F1 Automation Overhaul.

Implements the Strategy Pattern for outbound notifications, allowing
multiple channels (email, Discord) to be added or removed independently
without modifying the dispatcher core. Each channel encapsulates its
own transport, serialization, and error handling.

Design rationale:
    - Strategy Pattern: NotificationChannel (Protocol) defines the interface.
      Concrete implementations (GmailSMTPChannel, DiscordWebhookChannel) can be
      swapped or combined without touching NotificationDispatcher.
    - Gmail SMTP over Resend/SendGrid: No custom domain required. Uses Python's
      stdlib smtplib + ssl (no new dependencies). TLS encryption on port 465.
    - httpx for Discord: Already a project dependency. Async-capable for future
      real-time upgrades. Falls back gracefully if webhook URL is not configured.
    - All channels are optional: if credentials are missing, the channel is
      skipped with a WARNING log — the pipeline never fails due to notifications.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Protocol, runtime_checkable

import httpx

from f1_predictions.evaluation.post_race_verdict import RaceVerdict
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# Gmail SMTP configuration — port 465 uses implicit TLS (SMTP_SSL),
# which is more robust than port 587 STARTTLS for App Password auth.
_GMAIL_SMTP_HOST: str = "smtp.gmail.com"
_GMAIL_SMTP_PORT: int = 465

# Discord embed color codes aligned with verdict status.
_DISCORD_COLORS: dict[str, int] = {
    "excellent": 0x00C853,  # Green
    "good": 0xFFD600,  # Yellow
    "needs_improvement": 0xD50000,  # Red
    "unknown": 0x607D8B,  # Grey
}


@dataclass
class RaceBriefingPayload:
    """Structured payload passed to all notification channels.

    Attributes:
        verdict: The computed race accuracy verdict.
        html_body: Rendered HTML email body (from Jinja2 template).
        subject: Email subject line.
        chart_path: Optional path to the lap position PNG chart.
    """

    verdict: RaceVerdict
    html_body: str
    subject: str
    chart_path: Path | None = None


@runtime_checkable
class NotificationChannel(Protocol):
    """Abstract transport for outbound race briefings.

    Any class implementing `send(payload) -> bool` satisfies this protocol.
    Uses runtime_checkable so isinstance() checks work in tests.
    """

    def send(self, payload: RaceBriefingPayload) -> bool:
        """Deliver the race briefing via this channel's transport.

        Args:
            payload: The structured race briefing to deliver.

        Returns:
            True if delivery succeeded, False if it failed gracefully.
        """
        ...


class GmailSMTPChannel:
    """Delivers the race briefing as an HTML email via Gmail SMTP.

    Uses Python's stdlib smtplib with SMTP_SSL (port 465) and an
    App Password. No external SDK or domain verification required.

    Attributes:
        gmail_user: The Gmail address used as both sender and auth identity.
        app_password: The 16-character Google App Password (not the account
            password). Generate at myaccount.google.com/apppasswords.
        recipient_email: Destination email address.
    """

    def __init__(
        self,
        gmail_user: str,
        app_password: str,
        recipient_email: str,
    ) -> None:
        """Initialize the Gmail SMTP channel.

        Args:
            gmail_user: Sender Gmail address.
            app_password: Google App Password (16 chars, no spaces).
            recipient_email: Recipient email address.
        """
        self.gmail_user = gmail_user
        self.app_password = app_password
        self.recipient_email = recipient_email

    def send(self, payload: RaceBriefingPayload) -> bool:
        """Send the HTML email via Gmail SMTP_SSL.

        Constructs a MIME multipart/alternative message with both a plain-text
        fallback and the full HTML body, then authenticates and sends via TLS.

        Args:
            payload: The race briefing payload containing HTML body and subject.

        Returns:
            True on successful delivery, False if SMTP raises an exception.
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = payload.subject
        msg["From"] = f"F1 Intelligence System <{self.gmail_user}>"
        msg["To"] = self.recipient_email

        # Plain-text fallback for email clients that don't render HTML.
        plain_text = (
            f"F1 Race Briefing: {payload.verdict.gp_name}\n"
            f"MAE: {payload.verdict.mae_lap_time_s:.4f}s | "
            f"Status: {payload.verdict.status.upper()}\n"
            "Winner Prediction: "
            f"{'CORRECT' if payload.verdict.winner_correct else 'INCORRECT'}\n"
            f"Podium Accuracy: {payload.verdict.podium_accuracy_pct:.1f}%"
        )
        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(payload.html_body, "html"))

        context = ssl.create_default_context()
        try:
            with smtplib.SMTP_SSL(
                _GMAIL_SMTP_HOST, _GMAIL_SMTP_PORT, context=context
            ) as server:
                server.login(self.gmail_user, self.app_password)
                server.sendmail(
                    self.gmail_user,
                    self.recipient_email,
                    msg.as_string(),
                )
            logger.info(
                "Email sent successfully to %s (subject: %s)",
                self.recipient_email,
                payload.subject,
            )
        except smtplib.SMTPAuthenticationError:
            logger.exception(
                "Gmail SMTP auth failed. Check your App Password and ensure "
                "2-Step Verification is enabled on %s.",
                self.gmail_user,
            )
            return False
        except smtplib.SMTPException:
            logger.exception("Gmail SMTP error.")
            return False
        else:
            return True


class DiscordWebhookChannel:
    """Posts a compact race card embed to a Discord channel via Webhook.

    Uses httpx for a synchronous POST request. Discord embeds are limited
    to 6,000 characters total, so this channel sends a structured summary
    rather than the full HTML briefing.

    Attributes:
        webhook_url: The Discord Webhook URL (kept secret, never committed).
    """

    def __init__(self, webhook_url: str) -> None:
        """Initialize the Discord webhook channel.

        Args:
            webhook_url: Full Discord webhook URL.
        """
        self.webhook_url = webhook_url

    def send(self, payload: RaceBriefingPayload) -> bool:
        """Post a structured race card embed to Discord.

        Formats the verdict as a Discord embed with color-coded status,
        accuracy fields, and a key misses section.

        Args:
            payload: The race briefing payload.

        Returns:
            True on HTTP 204 response, False otherwise.
        """
        verdict = payload.verdict
        color = _DISCORD_COLORS.get(verdict.status, _DISCORD_COLORS["unknown"])

        winner_emoji = "✅" if verdict.winner_correct else "❌"
        fields = [
            {"name": "🏆 Winner Prediction", "value": winner_emoji, "inline": True},
            {
                "name": "📊 MAE (Lap Time)",
                "value": f"`{verdict.mae_lap_time_s:.4f}s`",
                "inline": True,
            },
            {
                "name": "📈 MAPE",
                "value": f"`{verdict.mape_pct:.2f}%`",
                "inline": True,
            },
            {
                "name": "🥇 Podium Accuracy",
                "value": f"`{verdict.podium_accuracy_pct:.1f}%`",
                "inline": True,
            },
            {
                "name": "🏎️ Top-10 Accuracy",
                "value": f"`{verdict.top10_accuracy_pct:.1f}%`",
                "inline": True,
            },
        ]
        if verdict.key_misses:
            fields.append(
                {
                    "name": "⚠️ Key Misses",
                    "value": ", ".join(verdict.key_misses),
                    "inline": False,
                }
            )

        embed = {
            "title": f"🏁 F1 Race Verdict: {verdict.gp_name}",
            "description": f"**Model Status**: `{verdict.status.upper()}`",
            "color": color,
            "fields": fields,
            "footer": {"text": "F1 Intelligence System • Powered by XGBoost + Gemini"},
        }

        try:
            response = httpx.post(
                self.webhook_url,
                json={"embeds": [embed]},
                timeout=10.0,
            )
            if response.status_code != 204:
                logger.warning(
                    "Discord webhook returned HTTP %d: %s",
                    response.status_code,
                    response.text,
                )
                return False
            logger.info("Discord notification sent successfully.")
        except httpx.RequestError:
            logger.exception("Discord webhook request failed.")
            return False
        else:
            return True


class NotificationDispatcher:
    """Orchestrates delivery across all registered notification channels.

    Iterates through registered channels and calls send() on each.
    Failures in one channel never propagate to others — the system is
    resilient by design. All results are logged.

    Attributes:
        channels: List of registered NotificationChannel implementations.
    """

    def __init__(self, channels: list[NotificationChannel]) -> None:
        """Initialize the dispatcher with a list of channels.

        Args:
            channels: List of notification channel implementations.
        """
        self.channels = channels

    def dispatch(self, payload: RaceBriefingPayload) -> dict[str, bool]:
        """Send the race briefing to all registered channels.

        Args:
            payload: The race briefing payload to dispatch.

        Returns:
            Dict mapping channel class name to delivery success status.
        """
        results: dict[str, bool] = {}
        for channel in self.channels:
            channel_name = type(channel).__name__
            logger.info("Dispatching via %s...", channel_name)
            results[channel_name] = channel.send(payload)

        successes = sum(results.values())
        logger.info(
            "Notification dispatch complete: %d/%d channels succeeded.",
            successes,
            len(self.channels),
        )
        return results
