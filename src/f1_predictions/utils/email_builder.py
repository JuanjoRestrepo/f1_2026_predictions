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

import math
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from f1_predictions.evaluation.post_race_verdict import RaceVerdict
from f1_predictions.utils.chart_exporter import chart_to_base64
from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# Path to the templates directory relative to this module's package root.
_TEMPLATES_DIR: Path = Path(__file__).parent.parent / "templates"
_BRIEFING_TEMPLATE: str = "race_briefing.html.j2"


def build_plaintext(verdict: RaceVerdict) -> str:
    """Render the plain-text email fallback body.

    Reports only what was actually measured. Preview/pending verdicts carry no
    accuracy, and a positional-only (``partial``) verdict carries no lap-time
    MAE — the plain-text body must never present those as real numbers
    (previously it printed "MAE: nans" and a fabricated winner line).

    Args:
        verdict: The race accuracy verdict.

    Returns:
        Multi-line plain-text body.
    """
    lines: list[str] = [
        f"F1 Race Briefing: {verdict.gp_name}",
        f"Status: {verdict.status.upper()}",
    ]

    if verdict.status in _NON_ACCURACY_STATUSES:
        lines.append("Prediction preview only - no measured accuracy is available yet.")
        return "\n".join(lines)

    if math.isnan(verdict.mae_lap_time_s):
        lines.append("MAE: N/A (lap-timing data unavailable)")
    else:
        lines.append(f"MAE: {verdict.mae_lap_time_s:.4f}s")
    if not math.isnan(verdict.mape_pct):
        lines.append(f"MAPE: {verdict.mape_pct:.2f}%")

    lines.append(
        f"Winner Prediction: {'CORRECT' if verdict.winner_correct else 'INCORRECT'}"
    )
    lines.append(f"Podium Accuracy: {verdict.podium_accuracy_pct:.1f}%")
    lines.append(f"Top-10 Accuracy: {verdict.top10_accuracy_pct:.1f}%")
    return "\n".join(lines)


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


# Statuses that carry no measured accuracy — the subject must not advertise an
# MAE or a winner outcome for these, since none was computed.
_NON_ACCURACY_STATUSES: frozenset[str] = frozenset({"preview", "unavailable"})

_STATUS_EMOJI: dict[str, str] = {
    "excellent": "✅",
    "good": "📊",
    "needs_improvement": "⚠️",
    "preview": "🔮",
    "unavailable": "⏳",
    "partial": "🟡",
}


def build_subject(verdict: RaceVerdict) -> str:
    """Construct the email subject line from the verdict.

    Args:
        verdict: The race accuracy verdict.

    Returns:
        Formatted subject string with status emoji. Measured-accuracy verdicts
        include the MAE and winner outcome; preview/pending verdicts include
        neither, because no accuracy was computed.
    """
    emoji = _STATUS_EMOJI.get(verdict.status, "🏁")
    if verdict.status in _NON_ACCURACY_STATUSES:
        return f"{emoji} F1 Briefing: {verdict.gp_name}"
    if verdict.status == "partial":
        # Positional accuracy only — no lap-time MAE was computable.
        return (
            f"{emoji} F1 Verdict: {verdict.gp_name} "
            f"| {'Winner ✓' if verdict.winner_correct else 'Winner ✗'} "
            f"(lap-time accuracy pending)"
        )
    return (
        f"{emoji} F1 Verdict: {verdict.gp_name} "
        f"| MAE {verdict.mae_lap_time_s:.4f}s "
        f"| {'Winner ✓' if verdict.winner_correct else 'Winner ✗'}"
    )
