import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from f1_predictions.utils.config import get_settings
from f1_predictions.utils.logging_setup import configure_root_pipeline_logger, get_logger

logger = get_logger(__name__)

def generate_visuals(year: int, event_name: str):
    """
    Generate a PNG chart and an HTML report for a specific GP and year.
    """
    settings = get_settings()
    
    # Standardize event name for filesystem (spaces to underscores)
    safe_event = event_name.replace(" ", "_")
    
    # Path resolution
    results_dir = Path(settings.reports_dir) / str(year) / safe_event / "results"
    standings_path = results_dir / "standings.csv"
    
    if not standings_path.exists():
        logger.error(f"Standings file not found at: {standings_path}")
        logger.info("Make sure the simulation has been run for this event and year.")
        return
        
    logger.info(f"Generating visuals for {event_name} {year}...")
    df = pd.read_csv(standings_path)
    
    # 1. Image Generation (Bar Chart)
    plt.figure(figsize=(12, 10))
    sns.set_style("darkgrid")
    
    # Sort for plot (fastest at top)
    df_plot = df.sort_values("median_predicted_s", ascending=False)
    
    # Dynamic color palette
    colors = sns.color_palette("rocket_r", len(df))
    
    bars = plt.barh(df_plot['Driver'], df_plot['median_predicted_s'], color=colors)
    
    # Labels and Titles
    plt.xlabel('Predicted Race Pace (s)', fontsize=12, fontweight='bold', labelpad=15)
    plt.title(f'{event_name} {year}\nPredicted Performance Ranking', fontsize=18, fontweight='bold', pad=25)
    
    # Axis Zoom
    min_time = df['median_predicted_s'].min()
    max_time = df['median_predicted_s'].max()
    plt.xlim(min_time - 0.5, max_time + 0.5)
    
    # Add time labels
    for bar in bars:
        width = bar.get_width()
        plt.text(width + 0.05, bar.get_y() + bar.get_height()/2, f'{width:.3f}s', 
                 va='center', fontsize=10, fontweight='bold')

    plt.tight_layout()
    img_filename = f"visual_ranking_{year}_{safe_event}.png"
    img_path = results_dir / img_filename
    plt.savefig(img_path, dpi=200, bbox_inches="tight")
    logger.info(f"Chart exported to: {img_path}")
    
    # 2. HTML Table Generation
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{event} {year} - Predictions</title>
        <style>
            :root {{
                --f1-red: #e10600;
                --bg-dark: #15151e;
                --card-bg: #1f1f27;
                --text-main: #ffffff;
                --text-dim: #949498;
                --accent: #00d2be;
            }}
            body {{ 
                font-family: 'Titillium Web', sans-serif, Arial; 
                background-color: var(--bg-dark); 
                color: var(--text-main); 
                padding: 40px; 
                margin: 0;
            }}
            .header {{
                text-align: center;
                border-bottom: 4px solid var(--f1-red);
                padding-bottom: 20px;
                margin-bottom: 40px;
            }}
            h1 {{ 
                font-size: 42px;
                margin: 0;
                text-transform: uppercase;
                letter-spacing: -1px;
            }}
            .subtitle {{
                color: var(--f1-red);
                font-weight: bold;
                letter-spacing: 2px;
                text-transform: uppercase;
            }}
            .container {{ max-width: 900px; margin: 0 auto; }}
            table {{ 
                width: 100%; 
                border-collapse: separate; 
                border-spacing: 0 8px;
            }}
            th {{ 
                text-align: left; 
                padding: 15px; 
                color: var(--text-dim);
                text-transform: uppercase;
                font-size: 12px;
                letter-spacing: 1px;
            }}
            tr {{ 
                background-color: var(--card-bg);
                transition: transform 0.2s;
            }}
            tr:hover {{
                transform: scale(1.02);
                background-color: #2a2a35;
            }}
            td {{ padding: 15px; }}
            td:first-child {{ border-radius: 8px 0 0 8px; border-left: 4px solid var(--f1-red); }}
            td:last-child {{ border-radius: 0 8px 8px 0; }}
            
            .rank {{ font-size: 24px; font-weight: 900; color: var(--f1-red); width: 60px; }}
            .driver-code {{ font-size: 20px; font-weight: bold; letter-spacing: 1px; }}
            .team {{ color: var(--text-dim); font-size: 14px; margin-top: 4px; }}
            .time {{ 
                font-family: monospace; 
                font-size: 18px; 
                color: var(--accent); 
                text-align: right;
                font-weight: bold;
            }}
            .footer {{
                margin-top: 50px;
                text-align: center;
                color: var(--text-dim);
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="subtitle">Predictive Simulation</div>
                <h1>{event} {year}</h1>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>Pos</th>
                        <th>Driver / Team</th>
                        <th style="text-align: right;">Predicted Pace</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            
            <div class="footer">
                Generated by Antigravity F1 Predictive Pipeline &copy; 2026
            </div>
        </div>
    </body>
    </html>
    """
    
    rows_html = ""
    for _, row in df.iterrows():
        rows_html += f"""
        <tr>
            <td class="rank">{int(row['rank'])}</td>
            <td>
                <div class="driver-code">{row['Driver']}</div>
                <div class="team">{row['Team']}</div>
            </td>
            <td class="time">{row['median_predicted_s']:.3f}s</td>
        </tr>
        """
        
    html_content = html_template.format(event=event_name, year=year, rows=rows_html)
    html_filename = f"report_{year}_{safe_event}.html"
    html_path = results_dir / html_filename
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    logger.info(f"HTML Report exported to: {html_path}")
    print(f"\nSuccess! Visuals generated for {event_name} ({year})")
    print(f"- Image: {img_path}")
    print(f"- HTML:  {html_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate visual reports for F1 predictions.")
    parser.add_argument("--year", type=int, default=2026, help="Season year (e.g. 2026)")
    parser.add_argument("--event", type=str, required=True, help="Event name (e.g. 'Miami Grand Prix')")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    
    args = parser.parse_args()
    configure_root_pipeline_logger(level=args.log_level)
    
    generate_visuals(args.year, args.event)
