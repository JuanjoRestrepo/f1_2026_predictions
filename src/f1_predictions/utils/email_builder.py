"""Email body builder — orchestrates Jinja2 rendering + chart embedding.

Coordinates between the template engine (Jinja2), the chart exporter
(Plotly/Kaleido), and the post-race verdict to produce a complete,
ready-to-send HTML email body.

Design decisions:
    - Jinja2 over Python f-strings: supports conditional blocks, loops, and
      filters cleanly. Email templates need rich logic (if winner_correct,
      for driver in podium, etc.) that f-strings cannot express safely.
    - Chart embedding via base64 data URI: renders inline in Gmail/Outlook/
      Apple Mail without external image hosting or CID attachments. The
      base64 string adds ~30KB overhead per chart, acceptable for weekly emails.
    - Graceful degradation: if chart_path is None or chart export fails,
      the email renders without the chart section (template uses {% if %}).
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from f1_predictions.evaluation.post_race_verdict import RaceVerdict
from f1_predictions.utils.chart_exporter import chart_to_base64
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# Path to the templates directory relative to this module's package root.
_TEMPLATES_DIR: Path = Path(__file__).parent.parent / "templates"
_BRIEFING_TEMPLATE: str = "race_briefing.html.j2"


def build_email_html(
    verdict: RaceVerdict,
    predicted_podium: list[str] | None = None,
    actual_podium: list[str] | None = None,
    ai_narrative: str | None = None,
    chart_path: Path | None = None,
) -> str:
    """Render the race briefing HTML email body.

    Loads the Jinja2 template, injects verdict data, encodes the chart,
    and returns the complete HTML string ready for SMTP delivery.

    Args:
        verdict: The computed race accuracy verdict (post-race).
        predicted_podium: List of predicted driver abbreviations [P1, P2, P3].
        actual_podium: List of actual driver abbreviations [P1, P2, P3].
        ai_narrative: Optional Gemini-generated race narrative text.
        chart_path: Optional path to a pre-rendered lap position PNG chart.

    Returns:
        Rendered HTML string for the email body.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template(_BRIEFING_TEMPLATE)

    # Encode chart if path provided and file exists.
    chart_base64: str | None = None
    if chart_path is not None:
        try:
            chart_base64 = chart_to_base64(chart_path)
        except FileNotFoundError:
            logger.warning(
                "Chart file not found at %s — email will render without chart.",
                chart_path,
            )

    html: str = template.render(
        verdict=verdict,
        predicted_podium=predicted_podium or [],
        actual_podium=actual_podium or [],
        ai_narrative=ai_narrative,
        chart_base64=chart_base64,
    )
    logger.debug("Email HTML rendered (%d chars)", len(html))
    return html


def build_subject(verdict: RaceVerdict) -> str:
    """Construct the email subject line from the verdict.

    Args:
        verdict: The race accuracy verdict.

    Returns:
        Formatted subject string with status emoji and MAE.
    """
    emoji = {"excellent": "✅", "good": "📊", "needs_improvement": "⚠️"}.get(
        verdict.status, "🏁"
    )
    return (
        f"{emoji} F1 Verdict: {verdict.gp_name} "
        f"| MAE {verdict.mae_lap_time_s:.4f}s "
        f"| {'Winner ✓' if verdict.winner_correct else 'Winner ✗'}"
    )
