"""Unit tests for email_builder and chart_exporter utilities.

Tests focus on pure logic (subject generation, template rendering,
base64 encoding) without hitting SMTP, disk IO for charts, or real APIs.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest

from f1_predictions.evaluation.post_race_verdict import RaceVerdict
from f1_predictions.utils.email_builder import build_email_html, build_subject


@pytest.fixture()
def excellent_verdict() -> RaceVerdict:
    """Verdict with excellent status (MAE < 0.2s)."""
    return RaceVerdict(
        round=8,
        gp_name="Monaco Grand Prix",
        mae_lap_time_s=0.178,
        mape_pct=0.21,
        winner_correct=True,
        podium_accuracy_pct=100.0,
        top10_accuracy_pct=90.0,
        key_misses=[],
    )


@pytest.fixture()
def poor_verdict() -> RaceVerdict:
    """Verdict with needs_improvement status (MAE > 0.35s)."""
    return RaceVerdict(
        round=3,
        gp_name="Australian Grand Prix",
        mae_lap_time_s=0.512,
        mape_pct=0.65,
        winner_correct=False,
        podium_accuracy_pct=33.3,
        top10_accuracy_pct=50.0,
        key_misses=["VER", "HAM", "ALO"],
    )


class TestBuildSubject:
    """Tests for the email subject builder."""

    def test_excellent_subject_has_checkmark(
        self, excellent_verdict: RaceVerdict
    ) -> None:
        subject = build_subject(excellent_verdict)
        assert "✅" in subject
        assert "Monaco Grand Prix" in subject
        assert "Winner ✓" in subject

    def test_poor_subject_has_warning(self, poor_verdict: RaceVerdict) -> None:
        subject = build_subject(poor_verdict)
        assert "⚠️" in subject
        assert "Winner ✗" in subject

    def test_subject_contains_mae(self, excellent_verdict: RaceVerdict) -> None:
        subject = build_subject(excellent_verdict)
        assert "0.1780s" in subject

    def test_good_status_subject(self) -> None:
        v = RaceVerdict(5, "Spanish GP", 0.25, 0.3, True, 66.7, 80.0)
        subject = build_subject(v)
        assert "📊" in subject


class TestBuildEmailHtml:
    """Tests for the Jinja2 HTML email renderer."""

    def test_renders_gp_name(self, excellent_verdict: RaceVerdict) -> None:
        """GP name must appear in the rendered HTML."""
        html = build_email_html(excellent_verdict)
        assert "Monaco Grand Prix" in html

    def test_renders_round_number(self, excellent_verdict: RaceVerdict) -> None:
        """Round number must appear in the rendered HTML."""
        html = build_email_html(excellent_verdict)
        assert "8" in html

    def test_renders_mae_value(self, excellent_verdict: RaceVerdict) -> None:
        """MAE value should be formatted and present."""
        html = build_email_html(excellent_verdict)
        assert "0.1780" in html

    def test_no_chart_section_when_path_is_none(
        self, excellent_verdict: RaceVerdict
    ) -> None:
        """Chart section should not appear when chart_path is None."""
        html = build_email_html(excellent_verdict, chart_path=None)
        assert "data:image/png;base64," not in html

    def test_renders_ai_narrative_when_provided(
        self, excellent_verdict: RaceVerdict
    ) -> None:
        """AI narrative should appear in the HTML when provided."""
        narrative = "Antonelli dominated sector 2 with superior tyre management."
        html = build_email_html(excellent_verdict, ai_narrative=narrative)
        assert narrative in html

    def test_no_ai_section_when_narrative_is_none(
        self, excellent_verdict: RaceVerdict
    ) -> None:
        """AI section should not appear when narrative is None."""
        html = build_email_html(excellent_verdict, ai_narrative=None)
        assert "AI RACE ANALYSIS" not in html

    def test_renders_key_misses_when_present(self, poor_verdict: RaceVerdict) -> None:
        """Key misses section should be visible when there are misses."""
        html = build_email_html(poor_verdict)
        assert "VER" in html

    def test_renders_podium_comparison_when_provided(
        self, excellent_verdict: RaceVerdict
    ) -> None:
        """Podium section should show predicted and actual finishers."""
        html = build_email_html(
            excellent_verdict,
            predicted_podium=["ANT", "NOR", "LEC"],
            actual_podium=["ANT", "LEC", "NOR"],
        )
        assert "ANT" in html
        assert "Predicted" in html
        assert "Actual" in html

    def test_renders_valid_html_structure(self, excellent_verdict: RaceVerdict) -> None:
        """Rendered output must be a valid HTML document."""
        html = build_email_html(excellent_verdict)
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_graceful_degradation_missing_chart_file(
        self, excellent_verdict: RaceVerdict
    ) -> None:
        """Should render without chart section when chart file does not exist."""
        nonexistent_path = Path("/nonexistent/chart.png")
        html = build_email_html(excellent_verdict, chart_path=nonexistent_path)
        # Should still render — just without the chart
        assert "Monaco Grand Prix" in html
        assert "data:image/png;base64," not in html

    def test_chart_embedded_when_file_exists(
        self, excellent_verdict: RaceVerdict
    ) -> None:
        """Should embed chart as base64 data URI when PNG file exists."""
        # Create a minimal valid PNG (1x1 pixel) for testing.
        # This is a valid PNG header + IHDR + IDAT + IEND.
        minimal_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9Q"
            "DwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(minimal_png)
            tmp_path = Path(f.name)

        try:
            html = build_email_html(excellent_verdict, chart_path=tmp_path)
            assert "data:image/png;base64," in html
        finally:
            tmp_path.unlink(missing_ok=True)
