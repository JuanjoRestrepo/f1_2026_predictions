"""Unit tests for the notifications module.

All SMTP and HTTP calls are mocked — no real emails sent, no network
access required. Tests validate the Strategy Pattern implementation,
payload construction, and graceful failure handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from f1_predictions.evaluation.post_race_verdict import RaceVerdict
from f1_predictions.utils.notifications import (
    DiscordWebhookChannel,
    GmailSMTPChannel,
    NotificationChannel,
    NotificationDispatcher,
    RaceBriefingPayload,
)


@pytest.fixture()
def sample_verdict() -> RaceVerdict:
    """A realistic RaceVerdict for use across tests."""
    return RaceVerdict(
        round=8,
        gp_name="Monaco Grand Prix",
        mae_lap_time_s=0.178,
        mape_pct=0.21,
        winner_correct=True,
        podium_accuracy_pct=66.7,
        top10_accuracy_pct=80.0,
        key_misses=["ALO", "HUL"],
    )


@pytest.fixture()
def sample_payload(sample_verdict: RaceVerdict) -> RaceBriefingPayload:
    """A RaceBriefingPayload with minimal HTML."""
    return RaceBriefingPayload(
        verdict=sample_verdict,
        html_body="<html><body>Test briefing</body></html>",
        subject="✅ F1 Verdict: Monaco Grand Prix | MAE 0.1780s | Winner ✓",
        chart_path=None,
    )


class TestRaceVerdict:
    """Tests for RaceVerdict status classification."""

    def test_excellent_status_below_threshold(self) -> None:
        v = RaceVerdict(8, "Monaco GP", 0.178, 0.2, True, 66.7, 80.0)
        assert v.status == "excellent"

    def test_good_status_mid_range(self) -> None:
        v = RaceVerdict(8, "Monaco GP", 0.25, 0.3, False, 33.3, 60.0)
        assert v.status == "good"

    def test_needs_improvement_above_threshold(self) -> None:
        v = RaceVerdict(8, "Monaco GP", 0.5, 0.8, False, 0.0, 40.0)
        assert v.status == "needs_improvement"

    def test_to_dict_serializable(self, sample_verdict: RaceVerdict) -> None:
        d = sample_verdict.to_dict()
        assert d["round"] == 8
        assert d["gp_name"] == "Monaco Grand Prix"
        assert isinstance(d["mae_lap_time_s"], float)
        assert isinstance(d["winner_correct"], bool)
        assert isinstance(d["key_misses"], list)


class TestGmailSMTPChannel:
    """Tests for GmailSMTPChannel — SMTP calls are fully mocked."""

    def test_send_success(self, sample_payload: RaceBriefingPayload) -> None:
        """Should return True when SMTP login and sendmail succeed."""
        channel = GmailSMTPChannel(
            gmail_user="test@gmail.com",
            app_password="test-app-password",  # noqa: S106
            recipient_email="recipient@example.com",
        )
        mock_server = MagicMock()
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = channel.send(sample_payload)

        assert result is True

    def test_send_returns_false_on_auth_error(
        self, sample_payload: RaceBriefingPayload
    ) -> None:
        """Should return False on SMTPAuthenticationError, not raise."""
        import smtplib

        channel = GmailSMTPChannel("test@gmail.com", "wrong-pass", "to@example.com")
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            mock_smtp.return_value.__enter__ = MagicMock(
                side_effect=smtplib.SMTPAuthenticationError(535, b"Auth failed")
            )
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = channel.send(sample_payload)

        assert result is False

    def test_implements_notification_channel_protocol(self) -> None:
        """GmailSMTPChannel should satisfy the NotificationChannel protocol."""
        channel = GmailSMTPChannel("a@gmail.com", "pass", "b@example.com")
        assert isinstance(channel, NotificationChannel)


class TestDiscordWebhookChannel:
    """Tests for DiscordWebhookChannel — HTTP calls are mocked."""

    def test_send_success_on_204(self, sample_payload: RaceBriefingPayload) -> None:
        """Should return True when Discord webhook returns HTTP 204."""
        channel = DiscordWebhookChannel(
            webhook_url="https://discord.com/api/webhooks/123/abc"
        )
        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch("httpx.post", return_value=mock_response):
            result = channel.send(sample_payload)

        assert result is True

    def test_send_returns_false_on_non_204(
        self, sample_payload: RaceBriefingPayload
    ) -> None:
        """Should return False on non-204 responses."""
        channel = DiscordWebhookChannel("https://discord.com/api/webhooks/123/abc")
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch("httpx.post", return_value=mock_response):
            result = channel.send(sample_payload)

        assert result is False

    def test_implements_notification_channel_protocol(self) -> None:
        """DiscordWebhookChannel should satisfy the NotificationChannel protocol."""
        channel = DiscordWebhookChannel("https://discord.com/api/webhooks/x/y")
        assert isinstance(channel, NotificationChannel)


class TestNotificationDispatcher:
    """Tests for the Strategy Pattern dispatcher."""

    def test_dispatches_to_all_channels(
        self, sample_payload: RaceBriefingPayload
    ) -> None:
        """Should call send() on every registered channel."""

        class StubChannelA:
            def send(self, payload: RaceBriefingPayload) -> bool:
                return True

        class StubChannelB:
            def send(self, payload: RaceBriefingPayload) -> bool:
                return True

        ch_a = StubChannelA()
        ch_b = StubChannelB()
        dispatcher = NotificationDispatcher([ch_a, ch_b])  # type: ignore[arg-type]
        results = dispatcher.dispatch(sample_payload)

        assert len(results) == 2
        assert results["StubChannelA"] is True
        assert results["StubChannelB"] is True

    def test_failure_in_one_channel_does_not_stop_others(
        self, sample_payload: RaceBriefingPayload
    ) -> None:
        """A failing channel should not prevent subsequent channels from running."""

        class FailingChannel:
            called: bool = False

            def send(self, payload: RaceBriefingPayload) -> bool:
                return False

        class SucceedingChannel:
            called: bool = False

            def send(self, payload: RaceBriefingPayload) -> bool:
                self.called = True
                return True

        ch_fail = FailingChannel()
        ch_ok = SucceedingChannel()
        dispatcher = NotificationDispatcher([ch_fail, ch_ok])  # type: ignore[arg-type]
        results = dispatcher.dispatch(sample_payload)

        assert ch_ok.called is True
        assert results["FailingChannel"] is False
        assert results["SucceedingChannel"] is True

    def test_empty_channels_returns_empty_dict(
        self, sample_payload: RaceBriefingPayload
    ) -> None:
        """Dispatching with no channels should return an empty results dict."""
        dispatcher = NotificationDispatcher([])
        results = dispatcher.dispatch(sample_payload)
        assert results == {}
