"""Plotly-based static chart exporter for email-embeddable race visuals.

Rationale for Plotly + Kaleido over Matplotlib/Seaborn:
    - Plotly is already a project dependency (used in the Jupyter notebooks).
    - Kaleido renders Plotly figures to PNG server-side with no browser runtime
      required, unlike Chart.js (which needs Node canvas / Puppeteer).
    - Plotly's dark theme ('plotly_dark') matches the F1 dashboard aesthetic
      out-of-the-box, requiring minimal style overrides.
    - Seaborn/Matplotlib produces lower-quality output for dark themes and
      requires more manual configuration for F1 team colors.

Output: 900x500px PNG, base64-encoded for inline email embedding.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go  # type: ignore[import-untyped]

from f1_predictions.utils.logging_setup import get_logger

logger = get_logger(__name__)

# Official F1 2026 team colors — consistent with the Next.js dashboard.
# Source: official F1 team branding guidelines.
TEAM_COLORS: dict[str, str] = {
    "VER": "#3671C6",  # Red Bull
    "NOR": "#FF8000",  # McLaren
    "LEC": "#E8002D",  # Ferrari
    "SAI": "#E8002D",  # Ferrari
    "HAM": "#27F4D2",  # Mercedes
    "RUS": "#27F4D2",  # Mercedes
    "ANT": "#27F4D2",  # Mercedes (Antonelli)
    "PIA": "#FF8000",  # McLaren
    "ALO": "#358C75",  # Aston Martin
    "STR": "#358C75",  # Aston Martin
    "GAS": "#0090FF",  # Alpine
    "OCO": "#0090FF",  # Alpine
    "TSU": "#6692FF",  # Racing Bulls
    "LAW": "#6692FF",  # Racing Bulls
    "HUL": "#B6BABD",  # Haas
    "BEA": "#B6BABD",  # Haas
    "ALB": "#64C4FF",  # Williams
    "COL": "#64C4FF",  # Williams
    "ZHO": "#52E252",  # Kick Sauber
    "BOT": "#52E252",  # Kick Sauber
}

# Chart dimensions optimized for email clients (Gmail supports up to 600px wide).
_CHART_WIDTH: int = 900
_CHART_HEIGHT: int = 500


def export_position_chart_png(
    predictions_df: pd.DataFrame,
    output_path: Path,
    gp_name: str = "Grand Prix",
    width: int = _CHART_WIDTH,
    height: int = _CHART_HEIGHT,
) -> Path:
    """Render and save the predicted lap position chart as a PNG.

    Creates a multi-line chart showing each driver's predicted lap-by-lap
    position, styled with the official F1 dark theme and team colors.
    Y-axis is inverted so P1 appears at the top (broadcast convention).

    Args:
        predictions_df: DataFrame with columns ['Driver', 'LapNumber',
            'Predicted_Position']. One row per driver per lap.
        output_path: Absolute path where the PNG will be saved.
        gp_name: Grand Prix name for the chart title.
        width: Output image width in pixels.
        height: Output image height in pixels.

    Returns:
        The resolved output path of the saved PNG.

    Raises:
        ValueError: If required columns are missing from the DataFrame.
        ImportError: If kaleido is not installed.
    """
    required = {"Driver", "LapNumber", "Predicted_Position"}
    missing = required - set(predictions_df.columns)
    if missing:
        msg = f"predictions_df missing required columns: {missing}"
        raise ValueError(msg)

    fig = go.Figure()

    for driver in predictions_df["Driver"].unique():
        driver_df = predictions_df[predictions_df["Driver"] == driver].sort_values(
            "LapNumber"
        )
        color = TEAM_COLORS.get(driver, "#888888")
        fig.add_trace(
            go.Scatter(
                x=driver_df["LapNumber"],
                y=driver_df["Predicted_Position"],
                mode="lines",
                name=driver,
                line={"color": color, "width": 2},
                hovertemplate=(
                    f"<b>{driver}</b><br>Lap %{{x}}<br>P%{{y}}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_dark",
        title={
            "text": f"🏁 {gp_name} — Predicted Lap Positions",
            "font": {"size": 18, "color": "#FFFFFF"},
        },
        paper_bgcolor="#0a0a0f",
        plot_bgcolor="#0a0a0f",
        xaxis={
            "title": "Lap Number",
            "gridcolor": "#2a2a3f",
            "color": "#aaaaaa",
        },
        yaxis={
            "title": "Position",
            "autorange": "reversed",  # P1 at top (broadcast convention)
            "dtick": 1,
            "gridcolor": "#2a2a3f",
            "color": "#aaaaaa",
        },
        legend={
            "bgcolor": "rgba(0,0,0,0.5)",
            "bordercolor": "#333",
            "borderwidth": 1,
            "font": {"color": "#ffffff", "size": 10},
        },
        width=width,
        height=height,
        margin={"l": 60, "r": 20, "t": 60, "b": 60},
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_image(str(output_path), format="png", scale=2)
    logger.info("Chart exported to %s (%dx%d)", output_path, width, height)
    return output_path


def chart_to_base64(chart_path: Path) -> str:
    """Read a PNG file and return its base64-encoded string.

    Used to embed the chart inline in HTML emails (data URI scheme),
    which renders correctly in Gmail, Outlook, and Apple Mail without
    requiring external image hosting.

    Args:
        chart_path: Path to the PNG file.

    Returns:
        Base64-encoded string of the PNG content (without the data URI prefix).

    Raises:
        FileNotFoundError: If the chart PNG does not exist.
    """
    if not chart_path.exists():
        msg = f"Chart file not found: {chart_path}"
        raise FileNotFoundError(msg)

    with chart_path.open("rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    logger.debug("Encoded chart to base64 (%d chars)", len(encoded))
    return encoded
